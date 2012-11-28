from django.core.urlresolvers import reverse
from django.utils.translation import ugettext_lazy as _
from django.contrib import admin
from django.contrib.admin.util import unquote
from django.conf.urls.defaults import patterns, url
from django.shortcuts import redirect
from django.utils.functional import update_wrapper
from django.db.models import Q

from django_qbe.utils import pickle_encode, get_query_hash
from django_qbe.utils import admin_site

from .models import SavedQuery, SavedQueryPermission


class SavedQueryAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner', 'description', 'date_created', 'query_hash',
                    'run_link')

    def run_link(self, obj):
        info = self.model._meta.app_label, self.model._meta.module_name
        pickled = pickle_encode(obj.query_data)
        query_hash = get_query_hash(pickled)
        return u'<span class="nowrap"><a href="%s">%s</a> | <a href="%s">%s</a></span>' % \
            (reverse("admin:%s_%s_run" % info, args=(obj.pk,)), _("Run"),
             reverse("qbe_form", kwargs={'query_hash': query_hash}), _("Edit"))
    run_link.short_description = _("query")
    run_link.allow_tags = True

    def get_urls(self):
        def wrap(view):
            def wrapper(*args, **kwargs):
                return self.admin_site.admin_view(view)(*args, **kwargs)
            return update_wrapper(wrapper, view)
        info = self.model._meta.app_label, self.model._meta.module_name
        urlpatterns = patterns('',
            url(r'^(.+)/run/$', wrap(self.run_view), name='%s_%s_run' % info),
        )
        return urlpatterns + super(SavedQueryAdmin, self).get_urls()

    def save_model(self, request, obj, form, change):
        if not obj.query_hash:
            query_hash = request.GET.get("hash", "")
            obj.query_hash = query_hash
        obj.query_data = request.session["qbe_query_%s" % obj.query_hash]
        obj.save()

    def add_view(self, request, *args, **kwargs):
        query_hash = request.GET.get("hash", "")
        query_key = "qbe_query_%s" % query_hash
        if not query_key in request.session:
            return redirect("qbe_form")
        return super(SavedQueryAdmin, self).add_view(request, *args, **kwargs)

    def run_view(self, request, object_id, extra_context=None):
        obj = self.get_object(request, unquote(object_id))
        data = obj.query_data
        pickled = pickle_encode(data)
        query_hash = get_query_hash(pickled)
        query_key = "qbe_query_%s" % query_hash
        if not query_key in request.session:
            request.session[query_key] = data
        return redirect("qbe_results", query_hash)

    def queryset(self, request):
        '''Filters SavedQueries due to current user permissions
        '''

        queries = super(SavedQueryAdmin, self).queryset(request)
        # superuser sees all
        if request.user.is_superuser:
            return queries
        for query in queries.all():
            # owner sees his stuff, otherwise checking user permission
            if query.owner != request.user:
                try:
                    perm_q = Q(
                        Q(user=request.user) | Q(group__user=request.user)
                    ) & Q(can_run=True)
                    permission = SavedQueryPermission.objects.get(perm_q)
                except SavedQueryPermission.DoesNotExist:
                    queries = queries.exclude(pk=query.pk)
        return queries


class SavedQueryPermissionAdmin(admin.ModelAdmin):
    list_display = ('user', 'group', 'query', 'can_run')

admin_site.register(SavedQuery, SavedQueryAdmin)
admin_site.register(SavedQueryPermission, SavedQueryPermissionAdmin)
