from app.db.models import EventType
from app.monitor.diff import EventData, diff_product
from tests.factories import product, variant


def test_first_sighting_is_a_baseline_with_no_restock_burst():
    new = product(variant("1"), variant("2"), variant("3"))

    assert diff_product(None, new) == [EventData(type=EventType.NEW_PRODUCT)]


def test_nothing_changed_means_no_events():
    snapshot = product(variant("1", available=True), variant("2", available=False))

    assert diff_product(snapshot, snapshot) == []


def test_restock():
    old = product(variant("1", available=False))
    new = product(variant("1", available=True))

    assert diff_product(old, new) == [
        EventData(
            type=EventType.RESTOCK, variant_external_id="1", old_value="false", new_value="true"
        )
    ]


def test_sold_out():
    old = product(variant("1", available=True))
    new = product(variant("1", available=False))

    assert diff_product(old, new) == [
        EventData(
            type=EventType.SOLD_OUT, variant_external_id="1", old_value="true", new_value="false"
        )
    ]


def test_price_drop_records_old_and_new_cents():
    old = product(variant("1", price=26000))
    new = product(variant("1", price=19500))

    assert diff_product(old, new) == [
        EventData(
            type=EventType.PRICE_DROP, variant_external_id="1", old_value="26000", new_value="19500"
        )
    ]


def test_price_increase_is_not_an_event():
    old = product(variant("1", price=19500))
    new = product(variant("1", price=26000))

    assert diff_product(old, new) == []


def test_restock_at_a_lower_price_is_two_events():
    old = product(variant("1", available=False, price=26000))
    new = product(variant("1", available=True, price=19500))

    assert [e.type for e in diff_product(old, new)] == [EventType.RESTOCK, EventType.PRICE_DROP]


def test_only_the_changed_sizes_get_events():
    old = product(variant("9", available=False), variant("10", available=False), variant("11"))
    new = product(variant("9", available=True), variant("10", available=False), variant("11"))

    assert [(e.type, e.variant_external_id) for e in diff_product(old, new)] == [
        (EventType.RESTOCK, "9")
    ]


def test_new_size_in_stock_is_a_restock():
    old = product(variant("1"))
    new = product(variant("1"), variant("2", available=True))

    assert diff_product(old, new) == [
        EventData(type=EventType.RESTOCK, variant_external_id="2", old_value=None, new_value="true")
    ]


def test_new_size_that_is_sold_out_is_not_an_event():
    old = product(variant("1"))
    new = product(variant("1"), variant("2", available=False))

    assert diff_product(old, new) == []


def test_size_removed_while_in_stock_is_sold_out():
    old = product(variant("1"), variant("2", available=True))
    new = product(variant("1"))

    assert [(e.type, e.variant_external_id) for e in diff_product(old, new)] == [
        (EventType.SOLD_OUT, "2")
    ]


def test_size_removed_while_sold_out_is_not_an_event():
    old = product(variant("1"), variant("2", available=False))
    new = product(variant("1"))

    assert diff_product(old, new) == []
