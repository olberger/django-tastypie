from tastypie.utils.timezone import now
from django.contrib.auth.models import User
from django.db import models
from django.template.defaultfilters import slugify

# Import some bits needed for the RDF mapping
from rdflib import Literal, URIRef

class Entry(models.Model):
    user = models.ForeignKey(User)
    pub_date = models.DateTimeField(default=now)
    title = models.CharField(max_length=200)
    slug = models.SlugField()
    body = models.TextField()

    # Define the RDF view mapping
    _rdf_mapping = {
        # Some ontologies used below
        '_prefixes': {'dcterms': 'http://purl.org/dc/terms/',
                      # SIOC represents quite well this example of blog posts
                      'sioc': 'http://rdfs.org/sioc/ns#'},
        # The rdf:type of the resource
        '_type': 'sioc:Post',
        # Optional : a supplementary fragment appended to all resource URIs
        '_res_fragment': '#post',
        # Optional : generation of a owl:sameAs declaration
        '_sameas_path': '/posts/%s',
        '_sameas_pk': 'slug',
        # Then mapping for all fields
        # usually, foreignkeys will be mapped to URIRefs
        'title': ('dcterms:title', Literal),
        'user': ('sioc:has_creator', URIRef),
        'pub_date': ('dcterms:created', Literal),
        'body': ('sioc:content', Literal)
        }

    def __unicode__(self):
        return self.title

    def save(self, *args, **kwargs):
        # For automatic slug generation.
        if not self.slug:
            self.slug = slugify(self.title)[:50]

        return super(Entry, self).save(*args, **kwargs)
