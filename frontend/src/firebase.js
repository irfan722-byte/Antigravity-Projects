import { initializeApp } from "firebase/app";
import { getAuth } from "firebase/auth";

// Active Firebase Configuration
const firebaseConfig = {
  apiKey: "AIzaSyCVExzi2DQ0kFjNBosYxIFYxBvXVPsOdXI",
  authDomain: "skills-booster-e779e.firebaseapp.com",
  projectId: "skills-booster-e779e",
  storageBucket: "skills-booster-e779e.firebasestorage.app",
  messagingSenderId: "1003962396361",
  appId: "1:1003962396361:web:1ad879f821e672afd62718",
  measurementId: "G-82W3X0B9SH"
};

const app = initializeApp(firebaseConfig);
export const auth = getAuth(app);
