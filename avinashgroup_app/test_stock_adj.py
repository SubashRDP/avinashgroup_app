import frappe

def create_test_adjustment():
    """Create stock adjustment with gain and loss at 0 rate"""
    
    # Get items with stock
    items = frappe.db.sql("""
        SELECT item_code, warehouse, actual_qty 
        FROM `tabBin` 
        WHERE actual_qty > 0 
        LIMIT 2
    """, as_dict=1)
    
    if not items or len(items) < 2:
        return {"status": "error", "msg": "Not enough items with stock"}
    
    item1_code = items[0]['item_code']
    item1_warehouse = items[0]['warehouse']
    item1_qty_before = float(items[0]['actual_qty'])
    
    item2_code = items[1]['item_code']
    item2_warehouse = items[1]['warehouse']
    item2_qty_before = float(items[1]['actual_qty'])
    
    # Create Stock Adjustment
    adjustment = frappe.new_doc('Stock Adjustment')
    adjustment.doctype = 'Stock Adjustment'
    adjustment.company = frappe.get_cached_value('Global Defaults', None, 'default_company')
    
    # Add gain entry
    adjustment.append('items', {
        'item_code': item1_code,
        'warehouse': item1_warehouse,
        'qty': 10,  # Gain
        'valuation_rate': 0
    })
    
    # Add loss entry  
    adjustment.append('items', {
        'item_code': item2_code,
        'warehouse': item2_warehouse,
        'qty': -5,  # Loss
        'valuation_rate': 0
    })
    
    adjustment.insert()
    adjustment.submit()
    
    # Verify stock changed
    item1_qty_after = frappe.db.get_value('Bin',
        {'item_code': item1_code, 'warehouse': item1_warehouse},
        'actual_qty') or 0
    
    item2_qty_after = frappe.db.get_value('Bin',
        {'item_code': item2_code, 'warehouse': item2_warehouse},
        'actual_qty') or 0
    
    return {
        "status": "success",
        "adjustment_id": adjustment.name,
        "items": [
            {
                "code": item1_code,
                "warehouse": item1_warehouse,
                "qty_before": item1_qty_before,
                "qty_after": item1_qty_after,
                "change": item1_qty_after - item1_qty_before,
                "expected": 10
            },
            {
                "code": item2_code,
                "warehouse": item2_warehouse,
                "qty_before": item2_qty_before,
                "qty_after": item2_qty_after,
                "change": item2_qty_after - item2_qty_before,
                "expected": -5
            }
        ]
    }

if __name__ == '__main__':
    result = create_test_adjustment()
    print(frappe.as_json(result))
