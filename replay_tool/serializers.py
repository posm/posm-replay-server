from rest_framework import serializers


class LocationSerializer(serializers.Serializer):
    lat = serializers.FloatField()
    lon = serializers.FloatField()
    x = serializers.IntegerField()
    y = serializers.IntegerField()


class TagSerializer(serializers.Serializer):
    k = serializers.CharField()
    v = serializers.CharField()


class NodeSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    version = serializers.IntegerField()
    changeset = serializers.IntegerField()
    deleted = serializers.BooleanField()
    timestamp = serializers.DateTimeField()
    uid = serializers.IntegerField()
    location = LocationSerializer()
    tags = TagSerializer(many=True)
    user = serializers.CharField()
    visible = serializers.BooleanField()
