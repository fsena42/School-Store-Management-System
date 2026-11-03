
from rest_framework import serializers
from .models import Request, RequestItem, Store, Item


class RequestItemSerializer(serializers.Serializer):
    item_id = serializers.IntegerField(min_value=1)
    quantity = serializers.IntegerField(min_value=1)

    def validate_item_id(self, value):
        if not Item.objects.filter(itemid=value).exists():
            raise serializers.ValidationError(
                "This item does not exist."
            )
        return value


class RequestSerializer(serializers.Serializer):
    store_id = serializers.IntegerField(min_value=1)
    items = RequestItemSerializer(many=True, allow_empty=False)

    def validate_store_id(self, value):
        if not Store.objects.filter(storeid=value).exists():
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

        allowed_stores = {
            2: [1],       # Cleaner → Cleaning Store
            1: [3],       # Teacher → Scholastics Store
            9: [1, 2],    # Chef → Cleaning and Food Stores
            8: [1, 2, 3], # Procurement Officer → all stores
            4: [1],       # Support Staff → Cleaning Store
            5: [1, 2, 3],    # Deputy Principal → Cleaning and Food Stores
            6: [1, 2, 3], # Principal → all stores
        }

        if store_id not in allowed_stores.get(position_id, []):
            raise serializers.ValidationError({
                "store_id": (
                    "Your position is not permitted to request "
                    "from this store."
                )
            })

        # Verify that every requested item belongs to the selected store.
        for item_data in attrs["items"]:
            item = Item.objects.filter(
                itemid=item_data["item_id"]
            ).first()

            if item is None:
                raise serializers.ValidationError({
                    "items": "One or more requested items do not exist."
                })

            if item.storeid_id != store_id:
                raise serializers.ValidationError({
                    "items": (
                        f"Item '{item.itemname}' does not belong "
                        "to the selected store."
                    )
                })

        return attrs
