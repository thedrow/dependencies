from ._attributes import Replace
from ._checks.circles import check_circles
from ._checks.injector import (
    check_attrs_redefinition,
    check_dunder_name,
    check_inheritance,
)
from ._checks.loops import check_loops
from ._replace import deep_replace_dependency
from ._spec import InjectorTypeType, make_dependency_spec
from .exceptions import DependencyError


class InjectorType(InjectorTypeType):
    def __new__(cls, class_name, bases, namespace):

        if not bases:
            namespace["__dependencies__"] = {}
            return type.__new__(cls, class_name, bases, namespace)

        check_inheritance(bases, Injector)
        ns = {}
        for attr in ("__module__", "__doc__", "__weakref__", "__qualname__"):
            try:
                ns[attr] = namespace.pop(attr)
            except KeyError:
                pass
        for k, v in namespace.items():
            check_dunder_name(k)
            check_attrs_redefinition(k)
        dependencies = {}
        for base in reversed(bases):
            dependencies.update(base.__dependencies__)
        for name, dep in namespace.items():
            dependencies[name] = make_dependency_spec(name, dep)
        check_loops(class_name, dependencies)
        check_circles(dependencies)
        ns["__dependencies__"] = dependencies
        return type.__new__(cls, class_name, bases, ns)

    def __getattr__(cls, attrname):
        __tracebackhide__ = True

        cache, cached = {"__self__": cls}, {"__self__"}
        current_attr, attrs_stack = attrname, [attrname]
        have_default = False

        while attrname not in cache:

            spec = cls.__dependencies__.get(current_attr)

            if spec is None:
                if have_default:
                    # FIXME: If first dependency have this name as
                    # default and the second one have this name
                    # without default, we will see a very strange
                    # KeyError about `cache` access.
                    cached.add(current_attr)
                    current_attr = attrs_stack.pop()
                    have_default = False
                    continue
                if len(attrs_stack) > 1:
                    message = "{0!r} can not resolve attribute {1!r} while building {2!r}".format(  # noqa: E501
                        cls.__name__, current_attr, attrs_stack.pop()
                    )
                else:
                    message = "{0!r} can not resolve attribute {1!r}".format(
                        cls.__name__, current_attr
                    )
                raise DependencyError(message)

            marker, attribute, args, have_defaults = spec

            if set(args).issubset(cached):
                kwargs = {k: cache[k] for k in args if k in cache}

                try:
                    cache[current_attr] = attribute(**kwargs)
                except Replace as replace:
                    deep_replace_dependency(cls, current_attr, replace)
                    # FIXME:
                    #
                    # We'll probably resolve weakref.  This happens because nested
                    # injector decide to replace a lazy import.  This nested injector
                    # is already resolved by its parent, so it contain a weakref in
                    # it.  Ideally we should not have parent in the scope at all.
                    #
                    # Also, `Replace` doesn't change dependencies dict of its parent,
                    # so lazy import will be evaluated again and again.  This kills
                    # the whole point of `Replace`.
                    check_loops(cls.__name__, cls.__dependencies__)
                    check_circles(cls.__dependencies__)
                    continue

                cached.add(current_attr)
                current_attr = attrs_stack.pop()
                have_default = False
                continue

            for n, arg in enumerate(args, 1):
                if arg not in cached:
                    attrs_stack.append(current_attr)
                    current_attr = arg
                    have_default = False if n < have_defaults else True
                    break

        return cache[attrname]

    def __setattr__(cls, attrname, value):

        raise DependencyError("'Injector' modification is not allowed")

    def __delattr__(cls, attrname):

        raise DependencyError("'Injector' modification is not allowed")

    def __contains__(cls, attrname):

        return attrname in cls.__dependencies__

    def __and__(cls, other):

        return type(cls.__name__, (cls, other), {})

    def __dir__(cls):

        parent = set(dir(cls.__base__))
        current = set(cls.__dict__) - set(["__dependencies__"])
        dependencies = set(cls.__dependencies__) - set(["__parent__"])
        attributes = sorted(parent | current | dependencies)
        return attributes


def __init__(self, *args, **kwargs):

    raise DependencyError("Do not instantiate Injector")


def let(cls, **kwargs):
    """Produce new Injector with some dependencies overwritten."""

    return type(cls.__name__, (cls,), kwargs)


injector_doc = """
Default dependencies specification DSL.

Classes inherited from this class may inject dependencies into classes
specified in it namespace.
"""


Injector = InjectorType(
    "Injector",
    (),
    {"__init__": __init__, "__doc__": injector_doc, "let": classmethod(let)},
)
