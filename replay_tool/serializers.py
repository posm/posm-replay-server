from rest_framework import serializers


from replay_tool.models import ReplayTool


class ReplayToolSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReplayTool
        fields = '__all__'


class LocationSerializer(serializers.Serializer):
    lat = serializers.FloatField()
    lon = serializers.FloatField()
    x = serializers.IntegerField()
    y = serializers.IntegerField()


class TagSerializer:
    def __init__(self, elem, many=False):
        self.many = many
        self.elem = elem

    @property
    def data(self):
        if self.many:
            return [{'k': x.k, 'v': x.v} for x in self.elem]
        return {'k': self.elem.k, 'v': self.elem.v}


class BaseElementSerializer:
    def __init__(self, elem, many=False):
        self.many = many
        self.elem = elem

    @classmethod
    def single(cls, elem):
        return {
            'id': elem.id,
            'version': elem.version,
            'changeset': elem.changeset,
            'deleted': elem.deleted,
            'timestamp': str(elem.timestamp),
            'uid': elem.uid,
            # 'user': elem.user,
            'tags': TagSerializer(elem.tags, many=True).data,
            'visible': elem.visible
        }

    @property
    def data(self):
        if self.many:
            return [self.single(x) for x in self.elem]
        return self.single(self.elem)


class NodeSerializer(BaseElementSerializer):
    pass


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
