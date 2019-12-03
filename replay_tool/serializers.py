from rest_framework import serializers


class LocationSerializer(serializers.Serializer):
    lat = serializers.FloatField()
    lon = serializers.FloatField()
    x = serializers.IntegerField()
    y = serializers.IntegerField()


class TagSerializer(serializers.Serializer):
    k = serializers.CharField()
    v = serializers.CharField()


class BaseElementSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    version = serializers.IntegerField()
    changeset = serializers.IntegerField()
    deleted = serializers.BooleanField()
    timestamp = serializers.DateTimeField()
    uid = serializers.IntegerField()
    user = serializers.CharField()
    tags = TagSerializer(many=True)
    visible = serializers.BooleanField()


class NodeSerializer(BaseElementSerializer):
    location = LocationSerializer()


class NodeRefSerializer(serializers.Serializer):
    ref = serializers.IntegerField()
    x = serializers.IntegerField()
    y = serializers.IntegerField()


class WaySerializer(BaseElementSerializer):
    nodes = NodeRefSerializer(many=True)


class RelationMemberSerializer(serializers.Serializer):
    ref = serializers.IntegerField()
    role = serializers.CharField()
    type = serializers.CharField()


class RelationSerializer(BaseElementSerializer):
    members = RelationMemberSerializer(many=True)
