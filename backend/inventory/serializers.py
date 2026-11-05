
from rest_framework import serializers
from .models import Request, RequestItem, Store, Item, ItemArchive
from .permissions import REQUESTABLE_STORES_BY_POSITION


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

        if store_id not in REQUESTABLE_STORES_BY_POSITION.get(position_id, ()):
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
            latest_archive = ItemArchive.objects.filter(
                item_id=item.itemid
            ).order_by("-archived_at", "-pk").first()
            if latest_archive and latest_archive.action == "ARCHIVED":
                raise serializers.ValidationError({
                    "items": f"Archived item '{item.itemname}' cannot be requested."
                })

        return attrs
