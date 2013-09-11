# myapp/api/resources.py

from django.contrib.auth.models import User
from tastypie import fields
from tastypie.authorization import Authorization
from tastypie.resources import ModelResource, ALL, ALL_WITH_RELATIONS

from rdflib import Literal
from myapp.models import Entry

# Add bits necessary for RDF dehydratation / serialization
from myapp.api.rdfmodels import RdfModelResource, RDFModelResourceMetaclass
from myapp.api.serializers import RDFSerializer

class UserResource(ModelResource):
    class Meta:
        queryset = User.objects.all()
        resource_name = 'user'
        excludes = ['email', 'password', 'is_active', 'is_staff', 'is_superuser']
        #fields = ['username', 'first_name', 'last_name', 'last_login']
        #allowed_methods = ['get']
        filtering = {
            'username': ALL,
        }

# The base class is RdfModelResource instead of Tastypie's plain ModelResource
class EntryResource(RdfModelResource):
    # The metaclass which will dynamically define the dehydrate_foo methods for fields in the RDF mapping
    __metaclass__ = RDFModelResourceMetaclass

    user = fields.ForeignKey(UserResource, 'user')

    class Meta:
        queryset = Entry.objects.all()
        resource_name = 'entry'
        authorization= Authorization()
        filtering = {
            'user': ALL_WITH_RELATIONS,
            'pub_date': ['exact', 'lt', 'lte', 'gte', 'gt'],
        }

        # Add a pointer to the django model to go fetch the rdf mapping in its Meta
        django_model = Entry
        # RDF serialization, in addition to the classic ones
        serializer = RDFSerializer()

    def dehydrate_body(self, bundle):
        body = "MESSAGE: %s /MESSAGE" % bundle.data['body']
        return Literal(body)
