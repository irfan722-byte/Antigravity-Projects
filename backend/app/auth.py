import os
import urllib.request
import json
import jwt
import datetime
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from .database import get_db
from . import models

# Config for Firebase project ID
# Replace this with your actual Firebase Project ID!
FIREBASE_PROJECT_ID = os.getenv("FIREBASE_PROJECT_ID", "skills-booster-e779e")
GOOGLE_CERTS_URL = "https://www.googleapis.com/robot/v1/metadata/x509/securetoken@system.gserviceaccount.com"

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)

# Keep cached certificates in memory to avoid fetching on every API call (performance boost!)
cached_certs = {}
certs_expire_time = None

def get_google_public_certs() -> dict:
    """Fetch active Google public certificates from metadata service with local caching."""
    global cached_certs, certs_expire_time
    now = datetime.datetime.utcnow()
    
    if cached_certs and certs_expire_time and now < certs_expire_time:
        return cached_certs
        
    try:
        response = urllib.request.urlopen(GOOGLE_CERTS_URL)
        certs = json.loads(response.read().decode("utf-8"))
        
        # Parse Cache-Control header to determine expiration (defaults to 1 hour if not specified)
        cache_control = response.headers.get("Cache-Control", "")
        max_age = 3600
        for part in cache_control.split(","):
            if "max-age" in part:
                try:
                    max_age = int(part.split("=")[1])
                except Exception:
                    pass
                    
        cached_certs = certs
        certs_expire_time = now + datetime.timedelta(seconds=max_age)
        return cached_certs
    except Exception as e:
        # If network error, return empty or raise
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Unable to fetch Google public certificates for token validation: {str(e)}"
        )

def verify_firebase_token(token: str) -> dict:
    """
    Decodes and verifies a Firebase ID Token using Google's public keys.
    Validates token signature, audience, issuer, and expiration.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        # 1. Decode token header without verification to resolve the key ID ('kid')
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get("kid")
        if not kid:
            print("DEBUG: Missing 'kid' in unverified header")
            raise credentials_exception
            
        # 2. Retrieve corresponding public certificate
        certs = get_google_public_certs()
        x509_cert = certs.get(kid)
        if not x509_cert:
            print(f"DEBUG: No x509 certificate found for kid={kid}")
            raise credentials_exception
            
        # 3. Parse x509 certificate to extract the public key object (avoids platform key deserialization errors!)
        from cryptography.x509 import load_pem_x509_certificate
        cert_obj = load_pem_x509_certificate(x509_cert.encode("utf-8"))
        public_key = cert_obj.public_key()
            
        # 4. Decode and verify payload signature using Google's public key
        payload = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            audience=FIREBASE_PROJECT_ID,
            issuer=f"https://securetoken.google.com/{FIREBASE_PROJECT_ID}"
        )
        return payload
    except jwt.ExpiredSignatureError as e:
        print(f"DEBUG: Token expired error: {str(e)}")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired")
    except jwt.PyJWTError as jwt_err:
        print(f"DEBUG: PyJWTError: {str(jwt_err)}")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid authentication token: {str(jwt_err)}")
    except Exception as e:
        print(f"DEBUG: Unexpected error verifying token: {str(e)}")
        import traceback
        traceback.print_exc()
        raise credentials_exception

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> models.User:
    """Dependency injection that authenticates the user using their Firebase ID Token."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Missing or invalid authentication token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    if not token:
        raise credentials_exception
        
    payload = verify_firebase_token(token)
    firebase_uid = payload.get("sub")
    email = payload.get("email")
    
    if not firebase_uid:
        raise credentials_exception
        
    # Standard lookup: check if firebase_uid is linked
    user = db.query(models.User).filter(models.User.firebase_uid == firebase_uid).first()
    
    if not user and email:
        # Fallback linking: check if standard user was pre-populated by email
        user = db.query(models.User).filter(models.User.email == email.strip().lower()).first()
        if user:
            # Link Firebase account to the existing profile!
            user.firebase_uid = firebase_uid
            db.commit()
            db.refresh(user)
            
    if not user:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account is not registered. Please complete signup first."
        )
        
    return user

def get_current_admin(current_user: models.User = Depends(get_current_user)) -> models.User:
    """Dependency injection to enforce admin-only access."""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have administrative privileges"
        )
    return current_user
