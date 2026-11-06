
from rest_framework import serializers
from .permissions import REQUESTABLE_STORES_BY_POSITION
from .sql import fetch_one


class RequestItemSerializer(serializers.Serializer):
    item_id = serializers.IntegerField(min_value=1)
    quantity = serializers.IntegerField(min_value=1)

    def validate_item_id(self, value):
        if fetch_one("SELECT ItemID FROM item WHERE ItemID = %s", [value]) is None:
            raise serializers.ValidationError(
                "This item does not exist."
            )
        return value


class RequestSerializer(serializers.Serializer):
    store_id = serializers.IntegerField(min_value=1)
    items = RequestItemSerializer(many=True, allow_empty=False)

    def validate_store_id(self, value):
        if fetch_one("SELECT StoreID FROM store WHERE StoreID = %s", [value]) is None:
            raise serializers.ValidationError(
                "This store does not exist."
            )
        return value

    def validate(self, attrs):
        staff = self.context.get("staff")

        if staff is None:
            raise serializers.ValidationError(
                "Authenticated staff member is required."
            )

        position_id = staff.positionid_id
        store_id = attrs["store_id"]

        if store_id not in REQUESTABLE_STORES_BY_POSITION.get(position_id, ()):
            raise serializers.ValidationError({
                "store_id": (
                    "Your position is not permitted to request "
                    "from this store."
                )
            })

        # Verify that every requested item belongs to the selected store.
        for item_data in attrs["items"]:
            item = fetch_one(
                "SELECT ItemID, ItemName, StoreID, IsArchived FROM item WHERE ItemID = %s",
                [item_data["item_id"]],
            )

            if item is None:
                raise serializers.ValidationError({
                    "items": "One or more requested items do not exist."
                })

            if item["StoreID"] != store_id:
                raise serializers.ValidationError({
                    "items": (
                        f"Item '{item['ItemName']}' does not belong "
                        "to the selected store."
                    )
                })
            if item["IsArchived"]:
                raise serializers.ValidationError({
                    "items": f"Archived item '{item['ItemName']}' cannot be requested."
                })

        return attrs
