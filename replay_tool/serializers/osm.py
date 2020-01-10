from rest_framework import serializers


class LocationSerializer(serializers.Serializer):
    lat = serializers.FloatField()
    lon = serializers.FloatField()


class TagSerializer(serializers.Serializer):
    k = serializers.CharField()
    v = serializers.CharField()


class BaseElementSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    version = serializers.IntegerField()
    changeset = serializers.IntegerField()
    deleted = serializers.BooleanField()
    timestamp = serializers.CharField()
    uid = serializers.IntegerField()
    tags = TagSerializer(many=True)
    user = serializers.CharField()
    visible = serializers.BooleanField()


class NodeSerializer(BaseElementSerializer):
    location = LocationSerializer()


class NodeRefSerializer(serializers.Serializer):
    ref = serializers.IntegerField()


class WaySerializer(BaseElementSerializer):
    nodes = NodeRefSerializer(many=True)


class RelationMemberSerializer(serializers.Serializer):
    ref = serializers.IntegerField()
    role = serializers.CharField()
    type = serializers.CharField()


class RelationSerializer(BaseElementSerializer):
    members = RelationMemberSerializer(many=True)
