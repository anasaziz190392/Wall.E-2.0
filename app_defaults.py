from models import RFQ, SupplierProfile

DEFAULT_RFQ = RFQ()
DEFAULT_SUPPLIERS = [
    SupplierProfile(name="Apex Metals", opening_ask=58000, floor_price=41000,
                    standard_delivery_days=18, min_delivery_days=12, preferred_payment_days=30),
    SupplierProfile(name="Borealis Fabrication", opening_ask=54000, floor_price=44500,
                    standard_delivery_days=15, min_delivery_days=13, preferred_payment_days=45),
    SupplierProfile(name="CoreForge Industries", opening_ask=61000, floor_price=47000,
                    standard_delivery_days=12, min_delivery_days=10, preferred_payment_days=30),
]
