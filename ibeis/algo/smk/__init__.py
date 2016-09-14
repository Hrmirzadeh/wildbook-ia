# -*- coding: utf-8 -*-
# Autogenerated on 12:05:11 2016/09/14
# flake8: noqa
from __future__ import absolute_import, division, print_function, unicode_literals
from ibeis.algo.smk import match_chips5
from ibeis.algo.smk import smk_pipeline
from ibeis.algo.smk import vocab_indexer
import utool
print, rrr, profile = utool.inject2(__name__, '[ibeis.algo.smk]')


def reassign_submodule_attributes(verbose=True):
    """
    why reloading all the modules doesnt do this I don't know
    """
    import sys
    if verbose and '--quiet' not in sys.argv:
        print('dev reimport')
    # Self import
    import ibeis.algo.smk
    # Implicit reassignment.
    seen_ = set([])
    for tup in IMPORT_TUPLES:
        if len(tup) > 2 and tup[2]:
            continue  # dont import package names
        submodname, fromimports = tup[0:2]
        submod = getattr(ibeis.algo.smk, submodname)
        for attr in dir(submod):
            if attr.startswith('_'):
                continue
            if attr in seen_:
                # This just holds off bad behavior
                # but it does mimic normal util_import behavior
                # which is good
                continue
            seen_.add(attr)
            setattr(ibeis.algo.smk, attr, getattr(submod, attr))


def reload_subs(verbose=True):
    """ Reloads ibeis.algo.smk and submodules """
    if verbose:
        print('Reloading submodules')
    rrr(verbose=verbose)
    def wrap_fbrrr(mod):
        def fbrrr(*args, **kwargs):
            """ fallback reload """
            if verbose:
                print('No fallback relaod for mod=%r' % (mod,))
            # Breaks ut.Pref (which should be depricated anyway)
            # import imp
            # imp.reload(mod)
        return fbrrr
    def get_rrr(mod):
        if hasattr(mod, 'rrr'):
            return mod.rrr
        else:
            return wrap_fbrrr(mod)
    def get_reload_subs(mod):
        return getattr(mod, 'reload_subs', wrap_fbrrr(mod))
    get_rrr(match_chips5)(verbose=verbose)
    get_rrr(smk_pipeline)(verbose=verbose)
    get_rrr(vocab_indexer)(verbose=verbose)
    rrr(verbose=verbose)
    try:
        # hackish way of propogating up the new reloaded submodule attributes
        reassign_submodule_attributes(verbose=verbose)
    except Exception as ex:
        print(ex)
rrrr = reload_subs

IMPORT_TUPLES = [
    ('match_chips5', None),
    ('smk_pipeline', None),
    ('vocab_indexer', None),
]
"""
Regen Command:
    cd /home/joncrall/code/ibeis/ibeis/algo/smk
    makeinit.py --modname=ibeis.algo.smk
"""