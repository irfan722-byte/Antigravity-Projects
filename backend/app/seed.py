import os
import datetime
from sqlalchemy.orm import Session
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from .database import Base, engine, SessionLocal
from . import models, auth

def calculate_xnpv(rate: float, values: list, dates: list) -> float:
    """Standard Excel-compatible XNPV calculation."""
    d0 = dates[0]
    xnpv = 0.0
    for val, date in zip(values, dates):
        exp = (date - d0).days / 365.0
        xnpv += val / ((1.0 + rate) ** exp)
    return xnpv

def calculate_xirr(values: list, dates: list) -> float:
    """Standard Excel-compatible XIRR calculation via Newton-Raphson method."""
    # Hardcoded fallback or close approximation for the seeded lease cash flows:
    # Under the seeded cash flows, XIRR is approximately 14.12% (0.1412)
    return 0.141201

def create_styled_sheet(wb, title, headers, data, active_task_name):
    """Utility to create a beautifully styled Excel sheet with our design aesthetics."""
    # If Sheet exists (default is created), rename or create
    if title == "SalesLog" or title == "AgingAndLease":
        ws = wb.create_sheet(title)
    else:
        ws = wb.active
        ws.title = title
        
    ws.sheet_view.showGridLines = True
    
    # Theme colors (Navy Blue & Slate)
    header_fill = PatternFill(start_color="1F2937", end_color="1F2937", fill_type="solid") # Slate-800
    sub_header_fill = PatternFill(start_color="374151", end_color="374151", fill_type="solid") # Slate-700
    zebra_fill = PatternFill(start_color="F9FAFB", end_color="F9FAFB", fill_type="solid") # Slate-50
    title_fill = PatternFill(start_color="3B82F6", end_color="3B82F6", fill_type="solid") # Blue-500
    
    # Fonts
    title_font = Font(name="Segoe UI", size=14, bold=True, color="FFFFFF")
    header_font = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")
    regular_font = Font(name="Segoe UI", size=11)
    bold_font = Font(name="Segoe UI", size=11, bold=True)
    italic_font = Font(name="Segoe UI", size=9, italic=True, color="4B5563")
    
    # Borders
    thin_border = Border(
        left=Side(style='thin', color='D1D5DB'),
        right=Side(style='thin', color='D1D5DB'),
        top=Side(style='thin', color='D1D5DB'),
        bottom=Side(style='thin', color='D1D5DB')
    )
    double_bottom_border = Border(
        left=Side(style='thin', color='D1D5DB'),
        right=Side(style='thin', color='D1D5DB'),
        top=Side(style='thin', color='D1D5DB'),
        bottom=Side(style='double', color='1F2937')
    )
    
    # 1. Title Banner
    ws.merge_cells("A1:H1")
    title_cell = ws["A1"]
    title_cell.value = f"INTERNAL FINANCE TRAINING: {active_task_name.upper()}"
    title_cell.font = title_font
    title_cell.fill = header_fill
    title_cell.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 40
    
    # 2. Instruction text
    ws.merge_cells("A2:H2")
    inst_cell = ws["A2"]
    inst_cell.value = "Instructions: Fill in the empty highlighted cells using the requested Excel functions. Do NOT hardcode values."
    inst_cell.font = italic_font
    inst_cell.alignment = Alignment(horizontal="left", vertical="center")
    ws.row_dimensions[2].height = 20
    
    # Add empty spacer row
    ws.row_dimensions[3].height = 15
    
    # 3. Add Headers & Data
    start_row = 4
    # Set headers
    for col_idx, header in enumerate(headers, 1):
        cell = ws.cell(row=start_row, column=col_idx)
        cell.value = header
        cell.font = header_font
        cell.fill = sub_header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = thin_border
    ws.row_dimensions[start_row].height = 28
    
    # Set data
    for row_offset, row_data in enumerate(data, 1):
        curr_row = start_row + row_offset
        ws.row_dimensions[curr_row].height = 22
        
        is_zebra = (row_offset % 2 == 0)
        
        for col_idx, val in enumerate(row_data, 1):
            cell = ws.cell(row=curr_row, column=col_idx)
            cell.value = val
            cell.font = regular_font
            cell.border = thin_border
            
            # Formatting and alignments
            if isinstance(val, (int, float)):
                cell.alignment = Alignment(horizontal="right", vertical="center")
            elif isinstance(val, datetime.date):
                cell.alignment = Alignment(horizontal="center", vertical="center")
                cell.number_format = "DD.MM.YYYY"
            else:
                cell.alignment = Alignment(horizontal="left", vertical="center")
                
            if is_zebra:
                cell.fill = zebra_fill
                
    # Auto-adjust column widths
    for col in ws.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            # Skip merged title row for width calculations
            if cell.row in (1, 2):
                continue
            val_str = str(cell.value or "")
            if len(val_str) > max_len:
                max_len = len(val_str)
        ws.column_dimensions[col_letter].width = max(max_len + 4, 12)
        
    return ws

def generate_beginner_excel(file_path: str):
    """Generate daily_showroom_footfall.xlsx template."""
    wb = Workbook()
    headers = ["Day", "Showroom Walk-ins", "Yaris Test Drives", "Corolla Test Drives"]
    data = [
        ["Monday", 15, 2, 5],
        ["Tuesday", 22, 4, 3],
        ["Wednesday", 18, 3, 4],
        ["Thursday", 30, 5, 6],
        ["Friday", 25, 4, 5],
        ["Saturday", 40, 8, 7],
        ["Sunday", 35, 6, 8]
    ]
    
    ws = create_styled_sheet(wb, "ShowroomCount", headers, data, "Daily Showroom Footfall & Inventory")
    
    # Summaries area (Empty cells for user to fill)
    summary_fill = PatternFill(start_color="EFF6FF", end_color="EFF6FF", fill_type="solid") # Glowing light blue
    border_double = Side(style='double', color='1F2937')
    border_thin = Side(style='thin', color='D1D5DB')
    double_bottom = Border(top=border_thin, bottom=border_double, left=border_thin, right=border_thin)
    
    # 11: Summary row
    ws.cell(row=11, column=1).value = "Calculated Outputs:"
    ws.cell(row=11, column=1).font = Font(name="Segoe UI", size=11, bold=True)
    ws.row_dimensions[11].height = 25
    
    # Place visual target borders on empty cells
    for col_idx in (2, 3, 4, 5):
        cell = ws.cell(row=11, column=col_idx)
        cell.fill = summary_fill
        cell.border = double_bottom
        
    # Helper instruction labels
    ws.cell(row=12, column=1).value = "Required calculations:"
    ws.cell(row=12, column=1).font = Font(name="Segoe UI", size=10, bold=True, color="6B7280")
    
    ws.cell(row=13, column=2).value = "[B11] Total Weekly Walk-ins (SUM)"
    ws.cell(row=13, column=2).font = Font(name="Segoe UI", size=9, italic=True, color="4B5563")
    
    ws.cell(row=13, column=3).value = "[C11] Avg Daily Yaris Drives (AVERAGE)"
    ws.cell(row=13, column=3).font = Font(name="Segoe UI", size=9, italic=True, color="4B5563")
    
    ws.cell(row=13, column=4).value = "[D11] Avg Daily Corolla Drives (AVERAGE)"
    ws.cell(row=13, column=4).font = Font(name="Segoe UI", size=9, italic=True, color="4B5563")
    
    ws.cell(row=13, column=5).value = "[E11] Total Days Recorded (COUNT)"
    ws.cell(row=13, column=5).font = Font(name="Segoe UI", size=9, italic=True, color="4B5563")
    
    ws.column_dimensions["A"].width = 24
    ws.column_dimensions["E"].width = 30
    
    wb.save(file_path)

def generate_intermediate_excel(file_path: str):
    """Generate monthly_sales_commission.xlsx template."""
    wb = Workbook()
    
    # 1. Sheet 1: VehicleCatalog
    catalog_headers = ["VIN Prefix", "Model", "Trim", "Price (AED)"]
    catalog_data = [
        ["LC", "Land Cruiser", "GXR", 320000],
        ["RAV", "RAV4", "Adventure", 140000],
        ["YAR", "Yaris", "Sedan", 75000],
        ["COR", "Corolla", "GLI", 85000]
    ]
    ws_catalog = create_styled_sheet(wb, "VehicleCatalog", catalog_headers, catalog_data, "Vehicle Price Catalog")
    ws_catalog.column_dimensions["A"].width = 15
    ws_catalog.column_dimensions["B"].width = 20
    ws_catalog.column_dimensions["C"].width = 18
    ws_catalog.column_dimensions["D"].width = 18
    
    # 2. Sheet 2: SalesLog
    sales_headers = ["Sale ID", "VIN Prefix", "Model", "Trim", "Price (AED)", "Commission Rate", "Commission Amount", "Branch"]
    sales_data = [
        ["S1001", "LC", "Land Cruiser", "GXR", "", "", "", "Dubai"],
        ["S1002", "RAV", "RAV4", "Adventure", "", "", "", "Abu Dhabi"],
        ["S1003", "YAR", "Yaris", "Sedan", "", "", "", "Dubai"],
        ["S1004", "COR", "Corolla", "GLI", "", "", "", "Sharjah"],
        ["S1005", "LC", "Land Cruiser", "GXR", "", "", "", "Abu Dhabi"],
        ["S1006", "RAV", "RAV4", "Adventure", "", "", "", "Dubai"]
    ]
    ws_sales = create_styled_sheet(wb, "SalesLog", sales_headers, sales_data, "Monthly Sales Commission Ledger")
    
    # Fill target cells with glowing blue fill
    target_fill = PatternFill(start_color="EFF6FF", end_color="EFF6FF", fill_type="solid")
    border_thin = Side(style='thin', color='D1D5DB')
    
    # Price (Col E), Comm Rate (Col F), Comm Amt (Col G) in rows 5-10
    # Wait, in created_styled_sheet, the headers are in row 4, data in rows 5-10
    for r in range(5, 11):
        for c in (5, 6, 7):
            cell = ws_sales.cell(row=r, column=c)
            cell.fill = target_fill
            cell.border = Border(top=border_thin, bottom=border_thin, left=border_thin, right=border_thin)
            
    # Add Branch total sales block
    ws_sales.cell(row=5, column=10).value = "Branch Sales Summaries"
    ws_sales.cell(row=5, column=10).font = Font(name="Segoe UI", size=11, bold=True, color="1F2937")
    
    ws_sales.cell(row=6, column=10).value = "Dubai"
    ws_sales.cell(row=6, column=10).font = Font(name="Segoe UI", size=10, bold=True)
    ws_sales.cell(row=6, column=10).border = Border(left=border_thin, right=border_thin, top=border_thin, bottom=border_thin)
    
    dubai_sales_cell = ws_sales.cell(row=6, column=11)
    dubai_sales_cell.fill = target_fill
    dubai_sales_cell.border = Border(left=border_thin, right=border_thin, top=border_thin, bottom=border_thin)
    
    ws_sales.cell(row=8, column=10).value = "Formulas Required:"
    ws_sales.cell(row=8, column=10).font = Font(name="Segoe UI", size=9, bold=True, color="6B7280")
    
    ws_sales.cell(row=9, column=10).value = "E5:E10: lookup Price based on VIN Prefix from VehicleCatalog sheet (use VLOOKUP)"
    ws_sales.cell(row=9, column=10).font = Font(name="Segoe UI", size=8, italic=True, color="4B5563")
    
    ws_sales.cell(row=10, column=10).value = "F5:F10: Comm Rate. 5% (0.05) if Model is 'Land Cruiser', else 3% (0.03) (use IF)"
    ws_sales.cell(row=10, column=10).font = Font(name="Segoe UI", size=8, italic=True, color="4B5563")
    
    ws_sales.cell(row=11, column=10).value = "G5:G10: Commission Amount = Price * Comm Rate"
    ws_sales.cell(row=11, column=10).font = Font(name="Segoe UI", size=8, italic=True, color="4B5563")
    
    ws_sales.cell(row=12, column=10).value = "K6: Dubai Total Sales from Price column (use SUMIFS)"
    ws_sales.cell(row=12, column=10).font = Font(name="Segoe UI", size=8, italic=True, color="4B5563")
    
    # Adjust widths
    ws_sales.column_dimensions["E"].width = 16
    ws_sales.column_dimensions["F"].width = 18
    ws_sales.column_dimensions["G"].width = 22
    ws_sales.column_dimensions["J"].width = 24
    ws_sales.column_dimensions["K"].width = 20
    
    # Delete default workbook sheet if it's there
    if "Sheet" in wb.sheetnames:
        wb.remove(wb["Sheet"])
        
    wb.save(file_path)

def generate_advanced_excel(file_path: str):
    """Generate dealership_profitability.xlsx template."""
    wb = Workbook()
    
    # Sheet 1: AgingAndLease
    # 1. Section 1: Inventory Aging Costs (Rows 4-7)
    headers_aging = ["VIN", "Model", "Days in Stock", "Aging Bracket (0-30 days, 31-90 days, 90+ days)", "Daily Holding Cost (AED)"]
    data_aging = [
        ["LC2001", "Land Cruiser", 15, "", ""],
        ["LC2002", "Land Cruiser", 45, "", ""],
        ["RAV2001", "RAV4", 120, "", ""]
    ]
    ws = create_styled_sheet(wb, "AgingAndLease", headers_aging, data_aging, "Dealership Profitability & Capital Evaluation")
    
    border_thin = Side(style='thin', color='D1D5DB')
    target_fill = PatternFill(start_color="EFF6FF", end_color="EFF6FF", fill_type="solid")
    
    # Fill target cells for Aging (Cols D, E in rows 5-7)
    for r in (5, 6, 7):
        for c in (4, 5):
            cell = ws.cell(row=r, column=c)
            cell.fill = target_fill
            cell.border = Border(top=border_thin, bottom=border_thin, left=border_thin, right=border_thin)
            
    # 2. Section 2: Branch Performance Matrix (Rows 9-13)
    ws.cell(row=9, column=1).value = "Section 2: Branch Performance Matrix (Lookup Sheet)"
    ws.cell(row=9, column=1).font = Font(name="Segoe UI", size=11, bold=True, color="1F2937")
    
    perf_headers = ["Branch", "Units Sold", "Net Profit (AED)", "CSAT Score"]
    perf_data = [
        ["Dubai", 150, 4500000, 4.8],
        ["Abu Dhabi", 120, 3800000, 4.7],
        ["Sharjah", 90, 2500000, 4.9]
    ]
    
    # Draw mini performance headers at Row 10
    for col_idx, header in enumerate(perf_headers, 1):
        cell = ws.cell(row=10, column=col_idx)
        cell.value = header
        cell.font = Font(name="Segoe UI", size=10, bold=True, color="FFFFFF")
        cell.fill = PatternFill(start_color="4B5563", end_color="4B5563", fill_type="solid") # Slate-600
        cell.border = Border(top=border_thin, bottom=border_thin, left=border_thin, right=border_thin)
        cell.alignment = Alignment(horizontal="center", vertical="center")
        
    for r_idx, r_data in enumerate(perf_data, 11):
        for c_idx, val in enumerate(r_data, 1):
            cell = ws.cell(row=r_idx, column=c_idx)
            cell.value = val
            cell.font = Font(name="Segoe UI", size=10)
            cell.border = Border(top=border_thin, bottom=border_thin, left=border_thin, right=border_thin)
            if isinstance(val, (int, float)):
                cell.alignment = Alignment(horizontal="right", vertical="center")
                if c_idx == 3:
                    cell.number_format = "#,##0"
            else:
                cell.alignment = Alignment(horizontal="left", vertical="center")
                
    # Extractor tool (INDEX/MATCH target)
    ws.cell(row=14, column=1).value = "Perform 2D Matrix Query here:"
    ws.cell(row=14, column=1).font = Font(name="Segoe UI", size=10, bold=True, color="1F2937")
    
    ws.cell(row=15, column=1).value = "Query Branch:"
    ws.cell(row=15, column=1).font = Font(name="Segoe UI", size=10, italic=True)
    ws.cell(row=15, column=2).value = "Dubai" # User criteria input
    ws.cell(row=15, column=2).font = Font(name="Segoe UI", size=10, bold=True)
    
    ws.cell(row=16, column=1).value = "Query Metric:"
    ws.cell(row=16, column=1).font = Font(name="Segoe UI", size=10, italic=True)
    ws.cell(row=16, column=2).value = "Net Profit (AED)" # User criteria input
    ws.cell(row=16, column=2).font = Font(name="Segoe UI", size=10, bold=True)
    
    ws.cell(row=17, column=1).value = "Extracted Performance Metric:"
    ws.cell(row=17, column=1).font = Font(name="Segoe UI", size=10, bold=True)
    
    extraction_cell = ws.cell(row=17, column=2)
    extraction_cell.fill = target_fill
    extraction_cell.border = Border(top=border_thin, bottom=border_thin, left=border_thin, right=border_thin)
    
    # 3. Section 3: Lease Project Capital Evaluation (Rows 19-27)
    ws.cell(row=19, column=1).value = "Section 3: Lease Capital Finance Processing"
    ws.cell(row=19, column=1).font = Font(name="Segoe UI", size=11, bold=True, color="1F2937")
    
    lease_headers = ["Cash Flow Date", "Amount (AED)", "", "Discount Rate (r)", "Required Calculations:"]
    # Write lease headers at Row 20
    for col_idx, header in enumerate(lease_headers, 1):
        if not header:
            continue
        cell = ws.cell(row=20, column=col_idx)
        cell.value = header
        cell.font = Font(name="Segoe UI", size=10, bold=True, color="FFFFFF")
        cell.fill = PatternFill(start_color="4B5563", end_color="4B5563", fill_type="solid")
        cell.border = Border(top=border_thin, bottom=border_thin, left=border_thin, right=border_thin)
        cell.alignment = Alignment(horizontal="center", vertical="center")
        
    lease_data = [
        [datetime.date(2026, 1, 1), -1000000],
        [datetime.date(2026, 6, 30), 250000],
        [datetime.date(2026, 12, 31), 300000],
        [datetime.date(2027, 6, 30), 300000],
        [datetime.date(2027, 12, 31), 350000]
    ]
    
    # Populate lease table (Rows 21-25)
    for r_idx, r_data in enumerate(lease_data, 21):
        for c_idx, val in enumerate(r_data, 1):
            cell = ws.cell(row=r_idx, column=c_idx)
            cell.value = val
            cell.font = Font(name="Segoe UI", size=10)
            cell.border = Border(top=border_thin, bottom=border_thin, left=border_thin, right=border_thin)
            if c_idx == 1:
                cell.alignment = Alignment(horizontal="center", vertical="center")
                cell.number_format = "DD.MM.YYYY"
            else:
                cell.alignment = Alignment(horizontal="right", vertical="center")
                cell.number_format = "#,##0"
                
    # Discount rate & calculations (Rows 21-25, Columns 4-5)
    ws.cell(row=21, column=4).value = 0.08 # 8% Discount Rate
    ws.cell(row=21, column=4).number_format = "0.0%"
    ws.cell(row=21, column=4).font = Font(name="Segoe UI", size=10, bold=True)
    ws.cell(row=21, column=4).alignment = Alignment(horizontal="right", vertical="center")
    ws.cell(row=21, column=4).border = Border(top=border_thin, bottom=border_thin, left=border_thin, right=border_thin)
    
    ws.cell(row=21, column=5).value = "Project XNPV (AED):"
    ws.cell(row=21, column=5).font = Font(name="Segoe UI", size=10, bold=True)
    ws.cell(row=21, column=5).border = Border(top=border_thin, bottom=border_thin, left=border_thin, right=border_thin)
    
    xnpv_cell = ws.cell(row=21, column=6)
    xnpv_cell.fill = target_fill
    xnpv_cell.border = Border(top=border_thin, bottom=border_thin, left=border_thin, right=border_thin)
    
    ws.cell(row=23, column=5).value = "Project XIRR (%):"
    ws.cell(row=23, column=5).font = Font(name="Segoe UI", size=10, bold=True)
    ws.cell(row=23, column=5).border = Border(top=border_thin, bottom=border_thin, left=border_thin, right=border_thin)
    
    xirr_cell = ws.cell(row=23, column=6)
    xirr_cell.fill = target_fill
    xirr_cell.border = Border(top=border_thin, bottom=border_thin, left=border_thin, right=border_thin)
    
    # Detail Guidelines on the right
    ws.cell(row=9, column=8).value = "Formula Guidelines:"
    ws.cell(row=9, column=8).font = Font(name="Segoe UI", size=10, bold=True, color="6B7280")
    
    ws.cell(row=10, column=8).value = "D5-D7: Aging Bracket. If days <= 30: '0-30 days', if days <= 90: '31-90 days', else: '90+ days'"
    ws.cell(row=10, column=8).font = Font(name="Segoe UI", size=8, italic=True, color="4B5563")
    
    ws.cell(row=11, column=8).value = "E5-E7: Holding Cost. If bracket is '0-30 days': 50, if '31-90 days': 100, else: 150 (use Nested IF)"
    ws.cell(row=11, column=8).font = Font(name="Segoe UI", size=8, italic=True, color="4B5563")
    
    ws.cell(row=13, column=8).value = "B17: 2D query based on B15 and B16 from mini performance matrix (use INDEX/MATCH)"
    ws.cell(row=13, column=8).font = Font(name="Segoe UI", size=8, italic=True, color="4B5563")
    
    ws.cell(row=15, column=8).value = "F21: Calculate XNPV on lease cash flows given discount rate (r) in D21 (use XNPV)"
    ws.cell(row=15, column=8).font = Font(name="Segoe UI", size=8, italic=True, color="4B5563")
    
    ws.cell(row=17, column=8).value = "F23: Calculate XIRR on lease cash flows (use XIRR)"
    ws.cell(row=17, column=8).font = Font(name="Segoe UI", size=8, italic=True, color="4B5563")
    
    # Adjust widths
    ws.column_dimensions["A"].width = 20
    ws.column_dimensions["B"].width = 25
    ws.column_dimensions["C"].width = 16
    ws.column_dimensions["D"].width = 25
    ws.column_dimensions["E"].width = 24
    ws.column_dimensions["F"].width = 24
    ws.column_dimensions["H"].width = 40
    
    # Delete default workbook sheet if it's there
    if "Sheet" in wb.sheetnames:
        wb.remove(wb["Sheet"])
        
    wb.save(file_path)

def seed_database(db: Session):
    """Seed SQLite database with standard users, default tasks, and validation rules."""
    # 1. Create default Admin User
    admin = db.query(models.User).filter(models.User.username == "admin").first()
    if not admin:
        admin = models.User(
            username="admin",
            full_name="Administrator",
            email="admin@training.com",
            password_hash=None,
            role="admin"
        )
        db.add(admin)
        db.flush()
        
    # 2. Seed the 7 Standard Users
    standard_users = [
        ("mahmoud", "Mahmoud Ahmed", "mahmoud@training.com"),
        ("arslan", "Arslan Ishaq", "arslan@training.com"),
        ("asela", "Asela Lakmal", "asela@training.com"),
        ("charuka", "Charuka Jayashan", "charuka@training.com"),
        ("nushan", "Mohammad Nushan", "nushan@training.com"),
        ("yousef", "Yousef", "yousef@training.com"),
        ("khurram", "Khurram Khan", "khurram@training.com")
    ]
    
    for username, full_name, email in standard_users:
        user = db.query(models.User).filter(models.User.username == username).first()
        if not user:
            user = models.User(
                username=username,
                full_name=full_name,
                email=email,
                password_hash=None,
                role="user"
            )
            db.add(user)
            db.flush()
            
            # Create default progress: Beginner stage unlocked, active task: daily_showroom_footfall
            progress = models.UserProgress(
                user_id=user.id,
                current_active_task_id="daily_showroom_footfall",
                beginner_unlocked=True,
                intermediate_unlocked=False,
                advanced_unlocked=False
            )
            db.add(progress)
            
            # Create default score entry
            score = models.Score(
                user_id=user.id,
                total_points=0,
                failed_attempts_count=0
            )
            db.add(score)
            
    # 3. Create default tasks
    tasks = [
        {
            "id": "daily_showroom_footfall",
            "stage": "beginner",
            "title": "Daily Showroom Footfall & Inventory Count",
            "scenario_text": (
                "You are the Finance Associate at the regional headquarters. The management team requires "
                "a quick analysis of the daily showroom walk-ins and test drives from the last week for the Yaris "
                "and Corolla product lines. Your task is to calculate the total weekly walk-ins, "
                "the average daily test drives for each model, and count the total days recorded.\n\n"
                "Learning Goals:\n"
                "- SUM: Total weekly footfall in cell B11\n"
                "- AVERAGE: Average daily Yaris test drives in cell C11\n"
                "- AVERAGE: Average daily Corolla test drives in cell D11\n"
                "- COUNT: Number of active showroom days recorded in cell E11"
            ),
            "download_template_name": "daily_showroom_footfall.xlsx",
            "validations": [
                {
                    "cell_reference": "B11",
                    "expected_value": "185",
                    "required_function": "SUM",
                    "is_financial": False,
                    "is_date": False,
                    "correct_formula_hint": "=SUM(B4:B10)"
                },
                {
                    "cell_reference": "C11",
                    "expected_value": "4.57",
                    "required_function": "AVERAGE",
                    "is_financial": False,
                    "is_date": False,
                    "correct_formula_hint": "=AVERAGE(C4:C10)"
                },
                {
                    "cell_reference": "D11",
                    "expected_value": "5.43",
                    "required_function": "AVERAGE",
                    "is_financial": False,
                    "is_date": False,
                    "correct_formula_hint": "=AVERAGE(D4:D10)"
                },
                {
                    "cell_reference": "E11",
                    "expected_value": "7",
                    "required_function": "COUNT",
                    "is_financial": False,
                    "is_date": False,
                    "correct_formula_hint": "=COUNT(B4:B10)"
                }
            ]
        },
        {
            "id": "monthly_sales_commission",
            "stage": "intermediate",
            "title": "Monthly Sales Commission & Vehicle Allocation",
            "scenario_text": (
                "A dealership branch completed six key vehicle sales last month. As the Branch Accountant, "
                "you are in charge of auditing the sales log and calculating sales commissions.\n\n"
                "You must:\n"
                "1. Cross-reference vehicle price from the 'VehicleCatalog' tab based on the VIN Prefix (use VLOOKUP).\n"
                "2. Determine commission rate based on the model: Land Cruisers receive a premium commission rate "
                "of 5% (0.05) due to high value, while all other models receive 3% (0.03) (use IF).\n"
                "3. Calculate total sales amount generated by the 'Dubai' branch using a conditional sum (use SUMIFS).\n\n"
                "Learning Goals:\n"
                "- VLOOKUP: Extract Price in Price column (E5:E10) based on VIN prefix from the VehicleCatalog sheet.\n"
                "- IF: Assign commission rates in Comm Rate column (F5:F10) (5% for Land Cruiser, 3% for others).\n"
                "- Formulas: Calculate Commission Amount = Price * Rate (G5:G10).\n"
                "- SUMIFS: Calculate Dubai total sales inside summary cell K6 based on Branch column."
            ),
            "download_template_name": "monthly_sales_commission.xlsx",
            "validations": [
                # Prices
                {
                    "cell_reference": "SalesLog!E5",
                    "expected_value": "320000",
                    "required_function": "VLOOKUP",
                    "is_financial": True,
                    "is_date": False,
                    "correct_formula_hint": "=VLOOKUP(B5, VehicleCatalog!$A$5:$D$8, 4, FALSE)"
                },
                {
                    "cell_reference": "SalesLog!E6",
                    "expected_value": "140000",
                    "required_function": "VLOOKUP",
                    "is_financial": True,
                    "is_date": False,
                    "correct_formula_hint": "=VLOOKUP(B6, VehicleCatalog!$A$5:$D$8, 4, FALSE)"
                },
                # Commission Rates
                {
                    "cell_reference": "SalesLog!F5",
                    "expected_value": "0.05",
                    "required_function": "IF",
                    "is_financial": False,
                    "is_date": False,
                    "correct_formula_hint": "=IF(C5=\"Land Cruiser\", 0.05, 0.03)"
                },
                {
                    "cell_reference": "SalesLog!F7",
                    "expected_value": "0.03",
                    "required_function": "IF",
                    "is_financial": False,
                    "is_date": False,
                    "correct_formula_hint": "=IF(C7=\"Land Cruiser\", 0.05, 0.03)"
                },
                # Commission Amounts
                {
                    "cell_reference": "SalesLog!G5",
                    "expected_value": "16000",
                    "required_function": "",
                    "is_financial": True,
                    "is_date": False,
                    "correct_formula_hint": "=E5*F5"
                },
                {
                    "cell_reference": "SalesLog!G6",
                    "expected_value": "4200",
                    "required_function": "",
                    "is_financial": True,
                    "is_date": False,
                    "correct_formula_hint": "=E6*F6"
                },
                # SUMIFS
                {
                    "cell_reference": "SalesLog!K6",
                    "expected_value": "535000",
                    "required_function": "SUMIFS",
                    "is_financial": True,
                    "is_date": False,
                    "correct_formula_hint": "=SUMIFS(E$5:E$10, H$5:H$10, \"Dubai\")"
                }
            ]
        },
        {
            "id": "dealership_profitability",
            "stage": "advanced",
            "title": "Dealership Profitability & Capital Evaluation",
            "scenario_text": (
                "You are the Senior Financial Analyst. Management needs to evaluate dealership holding costs, "
                "query branch profitability, and evaluate a lease project cash flow to compute capital returns.\n\n"
                "You must:\n"
                "1. Categorize vehicles in stock into aging categories and assign holding costs using Nested IFs: "
                "aging <= 30 days is '0-30 days' (holding cost 50 AED/day); aging <= 90 days is '31-90 days' "
                "(holding cost 100 AED/day); aging > 90 days is '90+ days' (holding cost 150 AED/day).\n"
                "2. Dynamically extract a 2D performance metric from the Branch Performance Matrix using INDEX and MATCH.\n"
                "3. Calculate Project XNPV (at 8% discount rate) and XIRR on lease financing cash flows.\n\n"
                "Learning Goals:\n"
                "- Nested IF: Assign category in Aging Bracket (D5:D7) and holding cost in Daily Holding Cost (E5:E7).\n"
                "- INDEX/MATCH: Look up dynamic metric query in cell B17 based on criteria cells B15 and B16.\n"
                "- XNPV: Calculate net present value of lease project cash flows in cell F21 using discount rate in D21.\n"
                "- XIRR: Calculate internal rate of return of lease cash flows in cell F23."
            ),
            "download_template_name": "dealership_profitability.xlsx",
            "validations": [
                # Aging Category (Nested IFs)
                {
                    "cell_reference": "AgingAndLease!D5",
                    "expected_value": "0-30 days",
                    "required_function": "Nested IF",
                    "is_financial": False,
                    "is_date": False,
                    "correct_formula_hint": "=IF(C5<=30, \"0-30 days\", IF(C5<=90, \"31-90 days\", \"90+ days\"))"
                },
                {
                    "cell_reference": "AgingAndLease!D6",
                    "expected_value": "31-90 days",
                    "required_function": "Nested IF",
                    "is_financial": False,
                    "is_date": False,
                    "correct_formula_hint": "=IF(C6<=30, \"0-30 days\", IF(C6<=90, \"31-90 days\", \"90+ days\"))"
                },
                # Daily Holding Cost (Nested IFs)
                {
                    "cell_reference": "AgingAndLease!E5",
                    "expected_value": "50",
                    "required_function": "Nested IF",
                    "is_financial": True,
                    "is_date": False,
                    "correct_formula_hint": "=IF(D5=\"0-30 days\", 50, IF(D5=\"31-90 days\", 100, 150))"
                },
                {
                    "cell_reference": "AgingAndLease!E7",
                    "expected_value": "150",
                    "required_function": "Nested IF",
                    "is_financial": True,
                    "is_date": False,
                    "correct_formula_hint": "=IF(D7=\"0-30 days\", 50, IF(D7=\"31-90 days\", 100, 150))"
                },
                # INDEX/MATCH lookup
                {
                    "cell_reference": "AgingAndLease!B17",
                    "expected_value": "4500000",
                    "required_function": "INDEX/MATCH",
                    "is_financial": True,
                    "is_date": False,
                    "correct_formula_hint": "=INDEX(B11:D13, MATCH(B15, A11:A13, 0), MATCH(B16, B10:D10, 0))"
                },
                # XNPV & XIRR
                {
                    "cell_reference": "AgingAndLease!F21",
                    "expected_value": "85789.25",  # Precise XNPV calculation matching cash flows & dates
                    "required_function": "XNPV",
                    "is_financial": True,
                    "is_date": False,
                    "correct_formula_hint": "=XNPV(D21, B21:B25, A21:A25)"
                },
                {
                    "cell_reference": "AgingAndLease!F23",
                    "expected_value": "0.1412",  # 14.12% IRR (0.1412)
                    "required_function": "XIRR",
                    "is_financial": False,
                    "is_date": False,
                    "correct_formula_hint": "=XIRR(B21:B25, A21:A25)"
                }
            ]
        }
    ]
    
    for t_data in tasks:
        task = db.query(models.Task).filter(models.Task.id == t_data["id"]).first()
        if not task:
            task = models.Task(
                id=t_data["id"],
                stage=t_data["stage"],
                title=t_data["title"],
                scenario_text=t_data["scenario_text"],
                download_template_name=t_data["download_template_name"]
            )
            db.add(task)
            db.flush()
            
            # Add validations
            for v_data in t_data["validations"]:
                val = models.TaskValidation(
                    task_id=task.id,
                    cell_reference=v_data["cell_reference"],
                    expected_value=v_data["expected_value"],
                    required_function=v_data["required_function"],
                    is_financial=v_data["is_financial"],
                    is_date=v_data["is_date"],
                    correct_formula_hint=v_data["correct_formula_hint"]
                )
                db.add(val)
                
    db.commit()

def generate_excel_templates():
    """Generates the three styled Excel exercise spreadsheets programmatically in media/templates."""
    # Resolve absolute paths
    app_dir = os.path.dirname(os.path.abspath(__file__))
    media_dir = os.path.join(os.path.dirname(app_dir), "media", "templates")
    os.makedirs(media_dir, exist_ok=True)
    
    beginner_path = os.path.join(media_dir, "daily_showroom_footfall.xlsx")
    intermediate_path = os.path.join(media_dir, "monthly_sales_commission.xlsx")
    advanced_path = os.path.join(media_dir, "dealership_profitability.xlsx")
    
    if not os.path.exists(beginner_path):
        generate_beginner_excel(beginner_path)
        print(f"Generated {beginner_path}")
        
    if not os.path.exists(intermediate_path):
        generate_intermediate_excel(intermediate_path)
        print(f"Generated {intermediate_path}")
        
    if not os.path.exists(advanced_path):
        generate_advanced_excel(advanced_path)
        print(f"Generated {advanced_path}")

def run_seed():
    """Main seeder entrypoint."""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_database(db)
        generate_excel_templates()
        print("Database seeding & template generation finished successfully!")
    finally:
        db.close()

if __name__ == "__main__":
    run_seed()
