import datetime
import sys
import os

# Add parent directory to path to enable app imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import grader

class MockValidation:
    def __init__(self, ref, exp, req="", fin=False, dt=False, hint=""):
        self.cell_reference = ref
        self.expected_value = exp
        self.required_function = req
        self.is_financial = fin
        self.is_date = dt
        self.correct_formula_hint = hint

def test_numeric_parsing():
    print("Testing numeric parsing...")
    assert grader.parse_numeric_value(150) == 150.0
    assert grader.parse_numeric_value("1,250.50") == 1250.50
    assert grader.parse_numeric_value("AED 320,000.00") == 320000.00
    assert grader.parse_numeric_value(" $ 4,200.75 ") == 4200.75
    assert grader.parse_numeric_value(None) == 0.0
    assert grader.parse_numeric_value("invalid") == 0.0
    print("[OK] Numeric parsing tests passed!")

def test_date_parsing():
    print("Testing date parsing...")
    dt = datetime.datetime(2026, 5, 27, 14, 0, 0)
    d = datetime.date(2026, 5, 27)
    
    assert grader.parse_excel_date(dt) == "27.05.2026"
    assert grader.parse_excel_date(d) == "27.05.2026"
    assert grader.parse_excel_date("27.05.2026") == "27.05.2026"
    assert grader.parse_excel_date("2026-05-27") == "27.05.2026"
    assert grader.parse_excel_date("27/05/2026") == "27.05.2026"
    print("[OK] Date parsing tests passed!")

def test_function_checks():
    print("Testing function checks...")
    
    # 1. Standard SUM check
    pass_sum, _ = grader.check_function_usage("=SUM(B4:B10)", "SUM")
    assert pass_sum is True
    
    fail_sum, _ = grader.check_function_usage("=AVERAGE(B4:B10)", "SUM")
    assert fail_sum is False
    
    # 2. INDEX/MATCH check
    pass_im, _ = grader.check_function_usage("=INDEX(E10:G12, MATCH(B15, D10:D12, 0))", "INDEX/MATCH")
    assert pass_im is True
    
    fail_im, _ = grader.check_function_usage("=INDEX(E10:G12, VLOOKUP(B15, D10:D12, 2, FALSE))", "INDEX/MATCH")
    assert fail_im is False
    
    # 3. Nested IF check
    pass_nif, _ = grader.check_function_usage("=IF(C4<=30, \"0-30 days\", IF(C4<=90, \"31-90 days\", \"90+ days\"))", "Nested IF")
    assert pass_nif is True
    
    fail_nif, _ = grader.check_function_usage("=IF(C4<=30, \"0-30 days\", \"31-90 days\")", "Nested IF")
    assert fail_nif is False
    
    print("[OK] Function check tests passed!")

if __name__ == "__main__":
    print("Running grading engine unit tests...")
    test_numeric_parsing()
    test_date_parsing()
    test_function_checks()
    print("All unit tests passed successfully!")
