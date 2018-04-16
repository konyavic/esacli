#!/usr/bin/env python

import json
import os
import sys
import argparse
import dateutil.parser

from urllib.request import Request, urlopen
from urllib.parse import quote
from os.path import join as pathjoin
from os.path import expanduser as expanduser
from os.path import exists
from os.path import dirname
from functools import reduce
from hashlib import sha1
from collections import defaultdict

class Esa:
  def __init__(self):
    if "ESA_TOKEN" not in os.environ or "ESA_TEAM" not in os.environ: 
      raise Exception("ESA_TOKEN or ESA_TEAM is not set in the environment variables")

    self.token = os.environ["ESA_TOKEN"]
    self.team = os.environ["ESA_TEAM"]
    self.cache_dir = expanduser("~/.kyuujiki")
    os.system("mkdir -p %s" % self.cache_dir)

    self.cache_files = {
        "categories": pathjoin(self.cache_dir, "cache_categories.json"),
        }

  def has_cache(self):
    return exists(self.cache_files["categories"])

  def has_category_page_cache(self, category, page):
    category_hash = self.get_category_hash(category)
    return page in self.cache["posts"][category_hash]
  
  def do_flush_cache(self):
    os.system("rm -rf %s" % self.cache_dir)

  def get_category_hash(self, category):
    h = sha1()
    h.update(category.encode("utf-8"))
    return h.hexdigest()

  def get_cached_page_path(self, category_hash, page):
    category_path = pathjoin(self.cache_dir, "posts", category_hash)
    return pathjoin(category_path, str(page))

  def fetch_categories(self):
    q = Request("https://api.esa.io/v1/teams/%s/categories" % self.team)
    q.add_header("Authorization", "Bearer %s" % self.token)
    with open(self.cache_files["categories"], "wb") as f:
      f.write(urlopen(q).read())

  def fetch_posts_in_category(self, category, page=1):
    category_hash = self.get_category_hash(category)
    filepath = self.get_cached_page_path(category_hash, page)
    os.system("mkdir -p %s" % dirname(filepath))

    q = Request("https://api.esa.io/v1/teams/%s/posts?q=on:%s&page=%d" % (self.team, quote(category.encode("utf-8")), page))
    q.add_header("Authorization", "Bearer %s" % self.token)

    with open(filepath, "wb") as f:
      f.write(urlopen(q).read())
    
  def load_cache(self):
    self.cache = {}
    with open(self.cache_files["categories"], "r") as f:
      raw_categories = json.load(f)["categories"]
      self.cache["categories"] = {
          "name": "",
          "children": list(filter(lambda item: item["name"] != "", raw_categories)),
          "count": reduce(lambda s, item: "count" in item and item["count"] + s or s, raw_categories, 0),
          }

    self.cache["posts"] = defaultdict(dict)
    category_hash_list = os.listdir(pathjoin(self.cache_dir, "posts"))
    for category_hash in category_hash_list:
      page_list = os.listdir(pathjoin(self.cache_dir, "posts", category_hash))
      for page in page_list:
        filepath = self.get_cached_page_path(category_hash, page)
        with open(filepath, "r") as f:
          self.cache["posts"][category_hash][int(page)] = json.load(f)


  def _find_category_by_prefix(self, prefix):
    target_dirs = prefix.split("/")
    current_dir = self.cache["categories"]

    for target_dir in target_dirs:
      if not target_dir:
        continue 

      for item in current_dir["children"]:
        if item["name"] == target_dir:
          current_dir = item
          break

      if not current_dir["name"] == target_dir:
        return None

    return current_dir


  def do_ls_categories(self, prefix="", recursive=False):
    category = self._find_category_by_prefix(prefix)
    if not category:
      print("'%s' not found" % prefix)
      return

    def get_count(item):
      if "count" in item:
        return item["count"]
      else:
        return 0

    children = "children" in category and category["children"] or []
    digits = len(str(max([get_count(category)] 
      + list(map(get_count, children)))))
    digits = max(8, digits)
    
    def print_with_count(count, name):
      l = len(str(count))
      spaces = ' ' * (digits - l)
      print("%s%d %s" % (spaces, count, name))

    print_with_count(category["count"], "total items")
    for item in children:
      print_with_count(get_count(item), item["name"])

  def print_post_single_line(self, post):
    updated_at = dateutil.parser.parse(post["updated_at"]).strftime("%Y-%m-%d %H:%m:%S")
    print("https://%s.esa.io/posts/%d\t%s\t%s" % (self.team, post["number"], updated_at, post["name"]))


  def do_ls_post(self, prefix="", page=1):
    category_hash = self.get_category_hash(prefix)
    filepath = self.get_cached_page_path(category_hash, page)
    with open(filepath, "r") as f:
      self.cache["posts"][category_hash][page] = json.load(f)

    for post in self.cache["posts"][category_hash][page]["posts"]:
      self.print_post_single_line(post)

    return self.cache["posts"][category_hash][page]["next_page"]

  def do_ls_posts(self, prefix="", is_interactiv=True):
    page = 1
    while page:
      if not self.has_category_page_cache(prefix, page):
        if page and is_interactiv:
          input("press enter")
        print("no cached data, fetch again...")
        self.fetch_posts_in_category(prefix, page)
      else:
        print("use cached data")

      next_page = self.do_ls_post(prefix, page)
      if next_page:
        page = next_page
      else:
        page = None

def esa_flush(args):
  esa = Esa()
  esa.do_flush_cache()

def esa_ls(args):
  parser = argparse.ArgumentParser()
  parser.add_argument("--categories-only", "-c", action="store_true", help="list categories only")
  parser.add_argument("--posts-only", "-p", action="store_true", help="list posts only")
  parser.add_argument("--non-interactive", "-I", action="store_true", help="fetch all data at once")
  parser.add_argument("category", nargs="?", type=str, default="")
  args = parser.parse_args(args=args)
  
  esa = Esa()
  if not esa.has_cache():
    print("no cached data, fetch again...")
    esa.fetch_categories()
  else:
    print("use cached data")
  esa.load_cache()

  if not args.posts_only:
    esa.do_ls_categories(args.category)
  if not args.categories_only and not args.non_interactive:
    esa.do_ls_posts(args.category)

def esa_show(args):
  pass

def esa_tree(args):
  pass

SUBCOMMANDS = {
    "flush": esa_flush,
    "ls": esa_ls,
    "show": esa_show,
    "tree": esa_tree,
    }

if __name__ == "__main__":
  if len(sys.argv) < 2:
    print("usage: esa [command]")
    sys.exit(1)

  subcmd = sys.argv[1]
  if subcmd in SUBCOMMANDS:
    SUBCOMMANDS[subcmd](sys.argv[2:])
  else:
    print("unknown command '%s'" % subcmd)
    sys.exit(1)
