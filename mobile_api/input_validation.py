"""Small, field-keyed validators for endpoints not backed by model serializers."""
from rest_framework import serializers


def integer(value, name, *, minimum=1, maximum=9223372036854775807):
    try:
        return serializers.IntegerField(min_value=minimum, max_value=maximum).run_validation(value)
    except serializers.ValidationError as exc:
        raise serializers.ValidationError({name: exc.detail})


def decimal(value, name, *, maximum=None):
    try:
        return serializers.DecimalField(max_digits=14, decimal_places=2, min_value=0, max_value=maximum).run_validation(value)
    except serializers.ValidationError as exc:
        raise serializers.ValidationError({name: exc.detail})


def checkout_items(value, key):
    class Item(serializers.Serializer):
        quantity = serializers.IntegerField(min_value=1, max_value=20, default=1)
        note = serializers.CharField(max_length=300, required=False, allow_blank=True)

    class Items(serializers.Serializer):
        items = serializers.ListField(child=serializers.DictField(), allow_empty=False, max_length=100)

    container = Items(data={"items": value})
    container.is_valid(raise_exception=True)
    rows = []
    for raw in container.validated_data["items"]:
        item = Item(data=raw)
        item.is_valid(raise_exception=True)
        rows.append({**item.validated_data, key: integer(raw.get(key), key)})
    return rows
