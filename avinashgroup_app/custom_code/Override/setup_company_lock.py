"""
Quick Setup Script for Company Field Lock
Execute this from bench console after placing files in correct locations

Usage:
    bench --site your-site-name console
    >>> from avinashgroup_app.utils.setup_company_lock import quick_setup
    >>> quick_setup()
"""

import frappe
from frappe import _


def quick_setup():
    """
    Quick setup function to configure company field lock across all doctypes.
    This will:
    1. Update existing custom_company fields to be read-only after save
    2. Verify the setup
    3. Show a summary report
    """
    print("\n" + "="*60)
    print("Company Field Lock - Quick Setup")
    print("="*60 + "\n")
    
    try:
        # Import required modules
        from avinashgroup_app.custom_code.Override.company_field_lock import bulk_update_company_field_readonly
        from avinashgroup_app.utils.audit_file_manager import AuditBase
        
        print("Step 1: Gathering doctypes from AuditBase...")
        doctypes = AuditBase.doctypes
        print(f"Found {len(doctypes)} doctypes\n")
        
        print("Step 2: Updating company fields...")
        result = bulk_update_company_field_readonly(doctypes)
        
        print(f"\n✓ Successfully updated: {result['updated']} doctypes")
        
        if result['failed']:
            print(f"\n⚠ Failed to update {len(result['failed'])} doctypes:")
            for failed in result['failed'][:10]:  # Show first 10
                print(f"  - {failed}")
            if len(result['failed']) > 10:
                print(f"  ... and {len(result['failed']) - 10} more")
        
        print("\n" + "="*60)
        print("Setup Complete!")
        print("="*60)
        
        print("\nNext Steps:")
        print("1. Clear cache: bench --site your-site-name clear-cache")
        print("2. Restart bench: bench restart")
        print("3. Test with a document (e.g., Sales Invoice)")
        
        return result
        
    except ImportError as e:
        print(f"\n✗ Import Error: {str(e)}")
        print("\nPlease ensure:")
        print("1. company_field_lock.py is in avinashgroup_app/custom_code/")
        print("2. audit_file_manager.py has been updated with the import")
        return None
        
    except Exception as e:
        print(f"\n✗ Error: {str(e)}")
        frappe.log_error(frappe.get_traceback(), "Company Lock Setup Error")
        return None


def verify_setup():
    """
    Verifies the company field lock setup for all doctypes.
    Shows which doctypes have the lock configured correctly.
    """
    print("\n" + "="*60)
    print("Company Field Lock - Verification Report")
    print("="*60 + "\n")
    
    try:
        from avinashgroup_app.utils.audit_file_manager import AuditBase
        
        doctypes_checked = 0
        locked_count = 0
        unlocked_count = 0
        no_field_count = 0
        
        print(f"{'DocType':<35} {'Status':<20}")
        print("-" * 60)
        
        for doctype in sorted(AuditBase.doctypes):
            doctypes_checked += 1
            
            # Check for custom_company field
            custom_field = frappe.db.get_value(
                "Custom Field",
                {"dt": doctype, "fieldname": "custom_company"},
                ["name", "read_only_depends_on"],
                as_dict=True
            )
            
            # Check for standard company field
            meta = frappe.get_meta(doctype)
            has_standard_company = meta.has_field("company")
            
            if custom_field:
                if custom_field.read_only_depends_on:
                    print(f"{doctype:<35} {'✓ Locked':<20}")
                    locked_count += 1
                else:
                    print(f"{doctype:<35} {'⚠ Not Locked':<20}")
                    unlocked_count += 1
            elif has_standard_company:
                print(f"{doctype:<35} {'⊙ Standard Field':<20}")
                locked_count += 1
            else:
                print(f"{doctype:<35} {'✗ No Company Field':<20}")
                no_field_count += 1
        
        print("\n" + "="*60)
        print("Summary:")
        print(f"  Total Doctypes: {doctypes_checked}")
        print(f"  ✓ Locked: {locked_count}")
        print(f"  ⚠ Not Locked: {unlocked_count}")
        print(f"  ✗ No Company Field: {no_field_count}")
        print("="*60 + "\n")
        
        if unlocked_count > 0:
            print("⚠ Some doctypes are not locked. Run quick_setup() to fix.")
        else:
            print("✓ All doctypes are properly configured!")
        
        return {
            "total": doctypes_checked,
            "locked": locked_count,
            "unlocked": unlocked_count,
            "no_field": no_field_count
        }
        
    except Exception as e:
        print(f"\n✗ Error: {str(e)}")
        frappe.log_error(frappe.get_traceback(), "Company Lock Verification Error")
        return None


def fix_specific_doctype(doctype):
    """
    Fix the company field lock for a specific doctype.
    Useful for troubleshooting individual doctypes.
    
    Args:
        doctype (str): Name of the doctype to fix
    """
    try:
        from avinashgroup_app.custom_code.Override.company_field_lock import set_company_field_readonly_property
        
        print(f"\nFixing company field lock for: {doctype}")
        
        result = set_company_field_readonly_property(doctype)
        
        if result:
            frappe.db.commit()
            print(f"✓ Successfully updated {doctype}")
            print("Run: bench --site your-site-name clear-cache")
        else:
            print(f"✗ Failed to update {doctype}")
            print("Check the Error Log for details")
        
        return result
        
    except Exception as e:
        print(f"✗ Error: {str(e)}")
        frappe.log_error(frappe.get_traceback(), f"Fix {doctype} Error")
        return False


def test_validation():
    """
    Test the company field lock validation with a sample document.
    Creates a test document to verify the validation is working.
    """
    print("\n" + "="*60)
    print("Testing Company Field Lock Validation")
    print("="*60 + "\n")
    
    try:
        # Use a simple test case
        test_doctype = "Journal Entry"
        
        print(f"Creating a test {test_doctype}...")
        
        # Create a test document
        doc = frappe.get_doc({
            "doctype": test_doctype,
            "company": frappe.get_all("Company", limit=1)[0].name,
            "posting_date": frappe.utils.today()
        })
        
        doc.insert()
        original_company = doc.company
        
        print(f"✓ Created test document: {doc.name}")
        print(f"  Company: {original_company}")
        
        # Try to change the company
        print("\nAttempting to change company...")
        
        all_companies = frappe.get_all("Company", limit=2, pluck="name")
        if len(all_companies) < 2:
            print("⚠ Only one company exists. Cannot test company change.")
            doc.delete()
            return
        
        new_company = [c for c in all_companies if c != original_company][0]
        doc.company = new_company
        
        try:
            doc.save()
            print("✗ VALIDATION FAILED: Company change was allowed!")
            print("  Please check if validate_company_field_lock is properly configured")
        except frappe.ValidationError as e:
            print("✓ VALIDATION WORKING: Company change was blocked!")
            print(f"  Error message: {str(e)}")
        
        # Clean up
        print("\nCleaning up test document...")
        doc.reload()
        doc.delete()
        print("✓ Test complete")
        
    except Exception as e:
        print(f"✗ Test Error: {str(e)}")
        frappe.log_error(frappe.get_traceback(), "Company Lock Test Error")


def show_help():
    """Display help information for the setup functions."""
    help_text = """
╔════════════════════════════════════════════════════════════════╗
║            Company Field Lock - Setup Functions                ║
╚════════════════════════════════════════════════════════════════╝

Available Functions:
────────────────────────────────────────────────────────────────

1. quick_setup()
   - Automatically configures company field lock for all doctypes
   - Updates existing fields
   - Shows summary report
   
   Usage:
   >>> from avinashgroup_app.utils.setup_company_lock import quick_setup
   >>> quick_setup()

2. verify_setup()
   - Verifies which doctypes have company field lock configured
   - Shows detailed status for each doctype
   
   Usage:
   >>> from avinashgroup_app.utils.setup_company_lock import verify_setup
   >>> verify_setup()

3. fix_specific_doctype(doctype)
   - Fixes company field lock for a single doctype
   - Useful for troubleshooting
   
   Usage:
   >>> from avinashgroup_app.utils.setup_company_lock import fix_specific_doctype
   >>> fix_specific_doctype("Sales Invoice")

4. test_validation()
   - Tests if the validation is working properly
   - Creates a test document and tries to change company
   
   Usage:
   >>> from avinashgroup_app.utils.setup_company_lock import test_validation
   >>> test_validation()

5. show_help()
   - Displays this help message
   
   Usage:
   >>> from avinashgroup_app.utils.setup_company_lock import show_help
   >>> show_help()

────────────────────────────────────────────────────────────────
Recommended Setup Process:
────────────────────────────────────────────────────────────────

1. Run quick_setup() to configure all doctypes
2. Run verify_setup() to check the configuration
3. Clear cache: bench --site your-site clear-cache
4. Restart: bench restart
5. Test with a real document

────────────────────────────────────────────────────────────────
"""
    print(help_text)


# Auto-display help when module is imported
if __name__ != "__main__":
    print("\n💡 Type show_help() to see available setup functions")