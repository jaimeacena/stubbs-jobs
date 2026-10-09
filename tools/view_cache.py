"""Request-local memoization. Never cache decisions across reads or mutations."""
from contextvars import ContextVar
from contextlib import contextmanager
from functools import wraps

_cache=ContextVar('stubbs_jobs_view_cache',default=None)

@contextmanager
def snapshot():
    token=_cache.set({})
    try:yield
    finally:_cache.reset(token)

def memo(key,build):
    cache=_cache.get()
    if cache is None:return build()
    if key not in cache:cache[key]=build()
    return cache[key]

def cached(key):
    def decorate(fn):
        @wraps(fn)
        def wrapped(*args,**kwargs):
            return memo((fn.__module__,fn.__name__,key(*args,**kwargs)),lambda:fn(*args,**kwargs))
        return wrapped
    return decorate

def grouped(items,field):
    def build():
        result={}
        for item in items:result.setdefault(item.get(field),[]).append(item)
        return result
    return memo(('group',id(items),field),build)
