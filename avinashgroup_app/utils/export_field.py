import frappe
import pandas as pd
from datetime import datetime

def export_custom_fields_to_excel():
    """
    Export all custom fields (starting with 'custom_') from all DocTypes to Excel
    Excludes: custom_created_on, custom_created_by, custom_modified_by
    """
    
    # Fields to exclude
    excluded_fields = ['custom_created_on', 'custom_created_by', 'custom_modified_by','custom_company','custom_naming_series']
    
    # Get all Custom Field documents where fieldname starts with 'custom_'
    custom_fields = frappe.get_all(
        'Custom Field',
        filters=[
            ['fieldname', 'like', 'custom_%']
        ],
        fields=[
            'name',
            'dt',  # DocType
            'fieldname',
            'label',
            'fieldtype',
            'options',
            'reqd',
            'unique',
            'read_only',
            'hidden',
            'depends_on',
            'mandatory_depends_on',
            'read_only_depends_on',
            'default',
            'description',
            'in_list_view',
            'in_standard_filter',
            'in_global_search',
            'allow_in_quick_entry',
            'translatable',
            'insert_after',
            'idx',
            'owner',
            'creation',
            'modified',
            'modified_by'
        ],
        order_by='dt, idx'
    )
    
    # Filter out excluded fields and convert to dict
    filtered_fields = [
        dict(field) for field in custom_fields 
        if field.fieldname not in excluded_fields
    ]
    
    if not filtered_fields:
        print("No custom fields found!")
        return
    
    # Convert to DataFrame
    df = pd.DataFrame(filtered_fields)
    
    # Rename columns for better readability
    column_mapping = {
        'name': 'Custom Field ID',
        'dt': 'DocType',
        'fieldname': 'Field Name',
        'label': 'Label',
        'fieldtype': 'Field Type',
        'options': 'Options',
        'reqd': 'Mandatory',
        'unique': 'Unique',
        'read_only': 'Read Only',
        'hidden': 'Hidden',
        'depends_on': 'Depends On',
        'mandatory_depends_on': 'Mandatory Depends On',
        'read_only_depends_on': 'Read Only Depends On',
        'default': 'Default Value',
        'description': 'Description',
        'in_list_view': 'In List View',
        'in_standard_filter': 'In Standard Filter',
        'in_global_search': 'In Global Search',
        'allow_in_quick_entry': 'Allow in Quick Entry',
        'translatable': 'Translatable',
        'insert_after': 'Insert After',
        'idx': 'Position',
        'owner': 'Created By',
        'creation': 'Created On',
        'modified': 'Modified On',
        'modified_by': 'Modified By'
    }
    
    df.rename(columns=column_mapping, inplace=True)
    
    # Create filename with timestamp
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'custom_fields_export_{timestamp}.xlsx'
    filepath = frappe.get_site_path('private', 'files', filename)
    
    # Create Excel writer with multiple sheets
    with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
        # Write all custom fields to main sheet
        df.to_excel(writer, sheet_name='All Custom Fields', index=False)
        
        # Create a summary sheet grouped by DocType
        summary = df.groupby('DocType').agg({
            'Field Name': 'count',
            'Mandatory': lambda x: (x == 1).sum(),
            'Hidden': lambda x: (x == 1).sum(),
            'Read Only': lambda x: (x == 1).sum()
        }).reset_index()
        
        summary.columns = ['DocType', 'Total Fields', 'Mandatory Fields', 'Hidden Fields', 'Read Only Fields']
        summary = summary.sort_values('Total Fields', ascending=False)
        summary.to_excel(writer, sheet_name='Summary by DocType', index=False)
        
        # Auto-adjust column widths
        for sheet_name in writer.sheets:
            worksheet = writer.sheets[sheet_name]
            for column in worksheet.columns:
                max_length = 0
                column_letter = column[0].column_letter
                for cell in column:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except:
                        pass
                adjusted_width = min(max_length + 2, 50)
                worksheet.column_dimensions[column_letter].width = adjusted_width
    
    print(f"\n{'='*60}")
    print(f"✓ Export completed successfully!")
    print(f"{'='*60}")
    print(f"Total custom fields exported: {len(filtered_fields)}")
    print(f"Excluded fields: {', '.join(excluded_fields)}")
    print(f"File saved at: {filepath}")
    print(f"{'='*60}\n")
    
    # Print summary by DocType
    print("\nSummary by DocType:")
    print("-" * 60)
    doctype_count = df.groupby('DocType').size().sort_values(ascending=False)
    for doctype, count in doctype_count.items():
        print(f"  {doctype}: {count} custom fields")
    
    return filepath


def export_with_conditions():
    """
    Export custom fields with specific conditions/filters
    """
    
    excluded_fields = ['custom_created_on', 'custom_created_by', 'custom_modified_by','custom_company','custom_naming_series']
    
    # Example conditions - modify as needed
    conditions = [
        ['fieldname', 'like', 'custom_%'],
        # Add more conditions here, examples:
        # ['fieldtype', '=', 'Data'],  # Only Data type fields
        # ['reqd', '=', 1],  # Only mandatory fields
        # ['dt', 'in', ['Sales Order', 'Purchase Order']],  # Specific DocTypes
    ]
    
    custom_fields = frappe.get_all(
        'Custom Field',
        filters=conditions,
        fields='*',
        order_by='dt, idx'
    )
    
    # Filter out excluded fields and convert to dict
    filtered_fields = [
        dict(field) for field in custom_fields 
        if field.fieldname not in excluded_fields
    ]
    
    df = pd.DataFrame(filtered_fields)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'custom_fields_filtered_{timestamp}.xlsx'
    filepath = frappe.get_site_path('private', 'files', filename)
    
    df.to_excel(filepath, index=False)
    
    print(f"✓ Filtered export completed: {filepath}")
    print(f"Total records: {len(filtered_fields)}")
    
    return filepath


# Run the export
if __name__ == "__main__":
    # For basic export
    export_custom_fields_to_excel()
    
    # For export with additional conditions
    # export_with_conditions()