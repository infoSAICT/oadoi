from flask import make_response
from flask import request
from flask import redirect
from flask import abort
from flask import render_template
from flask import jsonify
from flask import g

import json
import os
import logging
import sys
import datetime

from app import app
from app import db

import product
import publication
from util import safe_commit


logger = logging.getLogger("views")


def json_dumper(obj):
    """
    if the obj has a to_dict() function we've implemented, uses it to get dict.
    from http://stackoverflow.com/a/28174796
    """
    try:
        return obj.to_dict()
    except AttributeError:
        return obj.__dict__


def json_resp(thing):
    json_str = json.dumps(thing, sort_keys=True, default=json_dumper, indent=4)

    if request.path.endswith(".json") and (os.getenv("FLASK_DEBUG", False) == "True"):
        logger.info(u"rendering output through debug_api.html template")
        resp = make_response(render_template(
            'debug_api.html',
            data=json_str))
        resp.mimetype = "text/html"
    else:
        resp = make_response(json_str, 200)
        resp.mimetype = "application/json"
    return resp


def abort_json(status_code, msg):
    body_dict = {
        "HTTP_status_code": status_code,
        "message": msg,
        "error": True
    }
    resp_string = json.dumps(body_dict, sort_keys=True, indent=4)
    resp = make_response(resp_string, status_code)
    resp.mimetype = "application/json"
    abort(resp)


#support CORS
@app.after_request
def add_crossdomain_header(resp):
    resp.headers['Access-Control-Allow-Origin'] = "*"
    resp.headers['Access-Control-Allow-Methods'] = "POST, GET, OPTIONS, PUT, DELETE, PATCH"
    resp.headers['Access-Control-Allow-Headers'] = "origin, content-type, accept, x-requested-with"

    # without this jason's heroku local buffers forever
    sys.stdout.flush()

    return resp



@app.before_request
def stuff_before_request():

    g.use_cache = True
    if ('no-cache', u'') in request.args.items():
        g.use_cache = False
        print "NOT USING CACHE"

    g.refresh = False
    if ('refresh', u'') in request.args.items():
        g.refresh = True
        print "REFRESHING THIS PUBLICATION IN THE DB"

    # don't redirect http api
    if request.url.startswith("http://api."):
        return


    # redirect everything else to https.
    new_url = None
    try:
        if request.headers["X-Forwarded-Proto"] == "https":
            pass
        elif "http://" in request.url:
            new_url = request.url.replace("http://", "https://")
    except KeyError:
        # print "There's no X-Forwarded-Proto header; assuming localhost, serving http."
        pass

    # redirect to naked domain from www
    if request.url.startswith("https://www.oadoi.org"):
        new_url = request.url.replace(
            "https://www.oadoi.org",
            "https://oadoi.org"
        )
        print u"URL starts with www; redirecting to " + new_url

    if new_url:
        return redirect(new_url, 301)  # permanent





# @todo remove, replaced by pub_resp_from_doi
# convenience function because we do this in multiple places
def give_doi_resp(doi):
    request_biblio = {"doi": doi}
    my_collection = product.run_collection_from_biblio(g.use_cache, **request_biblio)
    return jsonify({"results": my_collection.to_dict()})


# convenience function because we do this in multiple places
def give_post_resp():
    products = []
    body = request.json
    if "dois" in body:
        if len(body["dois"]) > 25:
            abort_json(413, "max number of DOIs is 25")
        for doi in body["dois"]:
            products += [product.build_product(g.use_cache, **{"doi": doi})]

    elif "biblios" in body:
        for biblio in body["biblios"]:
            products += [product.build_product(g.use_cache, **biblio)]

    my_collection = product.Collection()
    my_collection.products = products
    my_collection.set_fulltext_urls()
    return jsonify({"results": my_collection.to_dict()})





#temporary name
@app.route("/v1/REWRITE/publication/doi/<path:doi>", methods=["GET"])
def get_from_new_doi_endpoint(doi):
    my_pub = publication.get_pub_from_doi(doi, g.refresh)
    return jsonify({"results": my_pub.to_dict()})


# this is the old way of expressing this endpoint.
# the new way is POST api.oadoi.org/
# you can give it an object that lists DOIs
# you can also give it an object that lists biblios.
# this is undocumented and is just for impactstory use now.
@app.route("/v1/publications", methods=["POST"])
def post_publications_endpoint():
    return give_post_resp()


# this endpoint is undocumented for public use, and we don't really use it
# in production either.
# it's just for testing the POST biblio endpoint.
@app.route("/biblios", methods=["GET"])
@app.route("/v1/publication", methods=["GET"])
def get_from_biblio_endpoint():
    request_biblio = {}
    for (k, v) in request.args.iteritems():
        request_biblio[k] = v
    my_collection = product.run_collection_from_biblio(g.use_cache, **request_biblio)
    return jsonify({"results": my_collection.to_dict()})


# this is an old way of expressing this endpoint.
# the new way is api.oadoi.org/:doi
@app.route("/v1/publication/doi/<path:doi>", methods=["GET"])
def get_from_doi_endpoint(doi):
    return give_doi_resp(doi)

@app.route('/', methods=["GET", "POST"])
def index_endpoint():
    if request.method == "POST":
        return give_post_resp()

    if "://api." in request.url:
        return jsonify({
            "version": "1.1.0",
            "documentation_url": "https://oadoi.org/api",
            "msg": "Don't panic"
        })
    else:
        return render_template(
            'index.html'
        )


#  does three things:
#   the api response for GET /:doi
#   the (angular) web app, which handles all web pages
#   the DOI resolver (redirects to article)


@app.route("/<path:doi>", methods=["GET"])
def get_doi_redirect_endpoint(doi):

    # the GET api endpoint (returns json data)
    if "://api." in request.url:
        return give_doi_resp(doi)


    # the web interface (returns an SPA webpage that runs AngularJS)
    if not doi or not doi.startswith("10."):
        return index_endpoint()  # serve the angular app


    # the DOI resolver (returns a redirect)
    request_biblio = {"doi": doi}
    my_collection = product.run_collection_from_biblio(g.use_cache, **request_biblio)
    my_product = my_collection.products[0]
    return redirect(my_product.best_redirect_url, 302)  # 302 is temporary redirect


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True, threaded=True)

















