from datetime import date, time, timedelta

from sqlalchemy import select

from brightwater import models as m

CUSTOMERS = [
    ("BW-1041", "Helen Price", "homeowner", "07700 900714", None, "Standard reminder.", [
        ("18 Albert Road, Southsea, PO4 0JT", "Worcester Bosch", 2018, "service", "2026-12-12")]),
    ("BW-1056", "Graham Okafor", "landlord", "07700 900738", None, "Same-day properties preferred; tenants arrange access.", [
        ("22 Fawcett Road, PO4 0DH", "", None, "cp12", "2026-12-20"),
        ("9 Lucknow Street, PO1 1HJ", "", None, "cp12", "2026-12-24"),
        ("Flat 2, 41 Elm Grove, PO5 1JF", "", None, "cp12", "2026-12-28")]),
    ("BW-1072", "Joan Whitlock", "homeowner", "07700 900752", None, "Claire may answer; no assumed proxy authority.", [
        ("7 Laburnum Grove, Copnor, PO2 0HE", "Vaillant", 2015, "service", "2026-12-02")]),
    ("BW-1088", "Daniel Reeves", "homeowner", "07700 900766", None, "Historic complaint; £20 refund is not a new discount.", [
        ("31 Stubbington Avenue, PO2 0HY", "Ideal", 2019, "service", "2026-11-25")]),
    ("BW-1093", "Amira Haddad", "homeowner", "07700 900781", time(12), "No calls before noon.", [
        ("55 Festing Road, Southsea, PO4 0NQ", "Baxi", 2021, "service", "2026-12-01")]),
    ("BW-1107", "Peter Lund", "homeowner", "07700 900795", None, "Last contact 2024; number may be stale.", [
        ("14 Marmion Road, PO5 2BA", "Glow-worm", 2016, "service", "2026-12-08")]),
    ("BW-1112", "Kerry Walsh", "landlord", "07700 900809", None, "Usually combined £145 package.", [
        ("63 Kirby Road, PO2 0PE", "Vaillant", 2017, "combined", "2026-12-15")]),
    ("BW-1120", "Sanjay Mehta", "homeowner", "07700 900823", None, "Ageing boiler: one optional quote-interest question before the final booking readback.", [
        ("6 Highland Road, PO4 9DB", "Worcester Bosch", 2009, "service", "2026-12-10")]),
]


def seed(db):
    if db.scalar(select(m.Customer.id).limit(1)):
        return False
    for customer_id, name, kind, phone, preference, notes, properties in CUSTOMERS:
        db.add(m.Customer(id=customer_id, name=name, kind=kind, source_phone=phone,
                          not_before=preference, notes=notes))
        db.flush()
        for index, (address, boiler, year, service, due) in enumerate(properties):
            property_id = f"{customer_id}-P{index + 1}"
            db.add(m.Property(id=property_id, customer_id=customer_id, address=address,
                              boiler=boiler, boiler_year=year))
            db.flush()
            db.add(m.Obligation(id=f"{property_id}-O1", property_id=property_id,
                                service=service, due_date=date.fromisoformat(due)))
    for engineer_id, name, gas in [("dan", "Dan Hughes", True), ("priya", "Priya Shah", True), ("tom", "Tom Barker", False)]:
        db.add(m.Engineer(id=engineer_id, name=name, gas_registered=gas))
    db.flush()
    # The fixture books exactly half of job-hour capacity, with some full windows.
    # These are labelled diary blocks, never invented customer booking records.
    index = 0
    for offset in range(21):
        day = date(2026, 11, 16) + timedelta(days=offset)
        if day.weekday() > 4:
            continue
        for period in ["MORNING", "AFTERNOON"]:
            for engineer in ["dan", "priya"]:
                used = (180, 120, 60, 0)[index % 4]
                window = m.DiaryWindow(engineer_id=engineer, day=day, period=period, used_minutes=used)
                db.add(window)
                db.flush()
                if used:
                    db.add(m.DiaryBlock(window_id=window.id, minutes=used, source="assessment_prebooked_fixture"))
                index += 1
    db.add(m.Control(key="dialing", enabled=False))
    return True
