# Copyright (c) 2013, Olivier Berger + Institut Mines Telecom
# All rights reserved.

# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#     * Redistributions of source code must retain the above copyright
#       notice, this list of conditions and the following disclaimer.
#     * Redistributions in binary form must reproduce the above copyright
#       notice, this list of conditions and the following disclaimer in the
#       documentation and/or other materials provided with the distribution.
#     * Neither the name of the tastypie nor the
#       names of its contributors may be used to endorse or promote products
#       derived from this software without specific prior written permission.

# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL tastypie BE LIABLE FOR ANY
# DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
# (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
# ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

# RDF Model Resource base class and meta-class

import inspect
import urllib

from rdflib import Graph, Literal, BNode, Namespace, RDF, RDFS, URIRef, OWL, ConjunctiveGraph
from django.conf.urls import url
from django.core.urlresolvers import reverse 
from tastypie.resources import ModelResource
from tastypie import fields
from tastypie.bundle import Bundle
from myapp.api.serializers import RDFSerializer

# Dehydrate helper functions dynamically bound to dehydrate_FOO methods

def dehydratation_conversion_helper_URIRef(s, bundle):
    frame = inspect.currentframe()
    try:
        fieldname = frame.f_back.f_locals['field_name']
    finally:
        del frame
    if isinstance(bundle.data[fieldname], list):
        return map(lambda x: URIRef(x), bundle.data[fieldname])
    elif isinstance(bundle.data[fieldname], Bundle):
        return URIRef(bundle.data[fieldname].data['resource_uri'])
    else :
        return URIRef(bundle.data[fieldname])


def dehydratation_conversion_helper_Literal(s, bundle):
    frame = inspect.currentframe()
    try:
        fieldname = frame.f_back.f_locals['field_name']
    finally:
        del frame
    return Literal(bundle.data[fieldname])

# Metaclass that dynamically generates dehydrate_foo methods for
# resources, based on the '_rdf_mapping' declaration in the Django
# model's Meta class.
# It does some introspection to make this work... and may not be very
# maintainable...
class RDFModelResourceMetaclass(type):
    def __new__(cls, name, bases, dict):
        
        rdfmapping = None
        
        meta = dict.get('Meta')
        if hasattr(meta, 'django_model'):
            modelclass = meta.django_model
            if hasattr(modelclass, '_rdf_mapping'):
                rdfmapping = modelclass._rdf_mapping
        if rdfmapping:
            for fieldname in rdfmapping.keys():
                if fieldname[0] == '_':
                    continue
                predicate, objecttype = rdfmapping[fieldname]
                methodname = str("dehydrate_"+fieldname)
                if not dict.has_key(methodname):
                    if objecttype == Literal:
                        #print "OK: defining", modelclass.__name__ + '.' + methodname
                        dict[methodname] = dehydratation_conversion_helper_Literal
                    elif objecttype == URIRef:
                        #print "OK: defining", modelclass.__name__ + '.' + methodname
                        dict[methodname] = dehydratation_conversion_helper_URIRef
                    else:
                        print "Error: unknown RDFLib type for object", fieldname
                else:
                    print "Warning: overloading", modelclass.__name__ + '.' + methodname
                    
            if not dict.has_key('_model_rdf_mapping'):
                dict['_model_rdf_mapping'] = rdfmapping
                
        new = type(name, bases, dict)
        return new

# Base class for the Tastypie resources. It will handle the generation
# of a RDFLib Graph for dehydrated fields
class RdfModelResource(ModelResource):

    def __init__(self, api_name=None):
        super(RdfModelResource, self).__init__(api_name)
        self.rdf_graph = ConjunctiveGraph()
        
    @staticmethod
    def qname_to_predicate(qname, prefixes):
        pref, suf = qname.split(':',2)
        #        print pref, suf
        ns = prefixes[pref]
        predicate = ns[suf]
        return predicate
    
    def dehydrate(self, bundle):

        data = bundle.data
        g = Graph()
        mapping = self._model_rdf_mapping
        prefixes = mapping['_prefixes']
        
        
        for p in prefixes.keys():
            ns = Namespace(prefixes[p])
            g.bind(p, ns)
            prefixes[p]=ns
        
        fragment = mapping.get('_res_fragment', '')
        rdfres = URIRef(data['resource_uri']+fragment)
        
        type = self.__class__.qname_to_predicate(mapping['_type'], prefixes)
        g.add( (rdfres, RDF.type, type) )

        for k in data.keys():
            if k in mapping.keys():
                value = data[k]
                predicate, objecttype = mapping[k]
                frag = ''
                fragsplitted = predicate.split('#', 2)
                if len(fragsplitted) > 1:
                    frag = '#' + fragsplitted[1]
                predicate = fragsplitted[0] 
                predicate = self.__class__.qname_to_predicate(predicate, prefixes)
                if isinstance(value, list):
                    for i in value:
                        i = i + frag
                        g.add( (rdfres, predicate, i) )
                else :
                    value = value + frag
                    g.add( (rdfres, predicate, value) )
        
        # Until there's a proper way (in 0.10) to make prepend_url work for all related uris, do this
        sameaspk = mapping.get('_sameas_pk', None)
        sameaspath = mapping.get('_sameas_path', None)
        if sameaspk and sameaspath:
            g.bind('owl', OWL)
            sameasurl = sameaspath % str(data[sameaspk])
            sameasurl += fragment
            g.add( (rdfres, OWL.sameAs, URIRef(sameasurl)) )
        bundle.rdflib_graph = g
        self.rdfres = rdfres
        return bundle
    
    # Handles the lists of resources
    def alter_list_data_to_serialize(self, request, data):

        ADMSSW = Namespace('http://purl.org/adms/sw/')
        DCTERMS = Namespace('http://purl.org/dc/terms/')
        LDP = Namespace('http://www.w3.org/ns/ldp#')

        g = Graph()

        g.bind('dcterms', DCTERMS)
        g.bind('ldp', LDP)

        mapping = self._model_rdf_mapping
        prefixes = mapping['_prefixes']

        for p in prefixes.keys():
            ns = Namespace(prefixes[p])
            g.bind(p, ns)
            prefixes[p]=ns
        
        type = self.__class__.qname_to_predicate(mapping['_type'], prefixes)
        
        if isinstance(data, dict) :
            if 'objects' in data.keys():
                objects = data['objects']
                if isinstance(objects, list):
                    
                    resultsuri = URIRef(request.path + '#list')
                    
                    for b in objects:
                        if isinstance(b, Bundle):
                            bg = b.rdflib_graph
                            for p in bg.subjects(RDF.type, type):
                                g.add( (resultsuri, DCTERMS.hasPart, p ))
                    
            if 'meta' in data.keys():
                meta = data['meta']
                print meta
                if 'next' in meta.keys():
                    next = meta['next']
                    previous = meta['previous']
                    if next or previous:
                        if next:
                            nextUri = URIRef(meta['next'])
                        else:
                            nextUri = RDF.nil
                        ldppageuri = URIRef(request.get_full_path())
                        g.add( (ldppageuri, RDF.type, LDP.Page) )
                        g.add( (ldppageuri, LDP.nextPage, nextUri) )
                        g.add( (ldppageuri, LDP.pageOf, resultsuri) )   
                                
            data['rdflib_graph'] = g
                    
        return data 
                        
