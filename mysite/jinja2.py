# mysite.jinja2.

from jinja2 import Environment
# from django.contrib.staticfiles.storage import staticfiles_storage
from django.templatetags.static import static
from django.urls import reverse

from django.utils.timezone import localtime

def printLocalTime(dateTimeValue):
    return localtime(dateTimeValue).strftime("%d %B %Y %H:%M")

def environment(**options):
    env = Environment(**options)
    env.undefined="StrictUndefined"
    env.globals.update({
        # 'static': staticfiles_storage.url,
        'static': static,
        'url': reverse,
        "printLocalTime": printLocalTime,
    })
    return env