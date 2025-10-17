__version__ = "0.0.1"



# # Import and apply monkey patches when the app loads
# def apply_patches():
#     """Apply all monkey patches for ERPNext overrides"""
#     try:
#         from avinashgroup_app.custom_code.override_rounding import patch_sales_invoice_calculations
#         patch_sales_invoice_calculations()
#         print("✓ Sales Invoice calculation patches applied successfully")
#     except Exception as e:
#         print(f"✗ Error applying patches: {str(e)}")

# # Apply patches when module is imported
# apply_patches()
