"""Search module which provides handlers to locate users and proxy servers."""

import json

import flask

import ufo
from ufo.database import models
from ufo.handlers import auth


# TODO(eholder): Add tests for these in a separate PR.
@ufo.app.route('/searchpage/', methods=['GET'])
@ufo.setup_required
@auth.login_required
def search_page():
  """Renders the basic search page template.

  Returns:
    A rendered template of search.html.
  """
  search_text = json.loads(flask.request.args.get('search_text'))
  user_items = _search_user(search_text)
  proxy_server_items = _search_proxy_server(search_text)

  return flask.render_template(
      'search.html',
      user_items=json.dumps(user_items),
      proxy_server_items=json.dumps(proxy_server_items))

@ufo.app.route('/search/', methods=['GET'])
@ufo.setup_required
@auth.login_required
def search():
  """Gets the database entities matching the search term.

  Returns:
    A flask response json object with users set to the users found and servers
    set to the proxy servers found.
  """
  search_text = json.loads(flask.request.args.get('search_text'))
  results_dict = {
    'users': _search_user(search_text),
    'servers': _search_proxy_server(search_text),
  }
  results_json = json.dumps((results_dict))
  return flask.Response(ufo.XSSI_PREFIX + results_json,
                        headers=ufo.JSON_HEADERS)

def _search_user(search_text):
  """Gets the database users matching the search term.

  Args:
    search_text: A string for the search term.

  Returns:
    A dict object with items set to the users found.
  """
  results_dict = {
    'items': models.User.search(search_text),
  }
  return results_dict

def _search_proxy_server(search_text):
  """Gets the database proxy servers matching the search term.

  Args:
    search_text: A string for the search term.

  Returns:
    A dict object with items set to the proxy servers found.
  """
  results_dict = {
    'items': models.ProxyServer.search(search_text),
  }
  return results_dict
