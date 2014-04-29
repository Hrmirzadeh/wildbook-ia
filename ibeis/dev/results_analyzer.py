from __future__ import absolute_import, division, print_function
import utool
import numpy as np
from itertools import izip
from ibeis.dev import ibsfuncs
print, print_, printDBG, rrr, profile = utool.inject(__name__, '[resorg]', DEBUG=False)


def get_feat_matches(allres, qrid, rid):
    try:
        qres = allres.qrid2_qres[qrid]
        fm = qres.rid2_fm[rid]
    except KeyError:
        print('Failed qrid=%r, rid=%r' % (qrid, rid))
        raise
    return fm


def print_desc_distances_map(desc_distances_map):
    print('+-----------------------------')
    print('| DESCRIPTOR MATCHE DISTANCES:')
    for orgtype, distmap in desc_distances_map.iteritems():
        print('| orgtype(%r)' % (orgtype,))
        for disttype, dists in distmap.iteritems():
            print('|     disttype(%12r): %s' % (disttype, utool.printable_mystats(dists)))
    print('L-----------------------------')


def print_chipmatch_scores_map(desc_distances_map):
    print('+-----------------------------')
    print('| CHIPMATCH SCORES:')
    for orgtype, scores in desc_distances_map.iteritems():
        print('| orgtype(%r)' % (orgtype,))
        print('|     scores: %s' % (utool.printable_mystats(scores)))
    print('L-----------------------------')


def get_orgres_chipmatch_scores(allres, orgtype_list=['false', 'true']):
    orgres2_scores = {}
    for orgtype in orgtype_list:
        printDBG('[rr2] getting orgtype=%r distances between sifts' % orgtype)
        orgres = allres.get_orgtype(orgtype)
        ranks  = orgres.ranks
        scores = orgres.scores
        valid_scores = scores[ranks >= 0]  # None is less than 0
        orgres2_scores[orgtype] = valid_scores
    return orgres2_scores


def get_orgres_desc_match_dists(allres, orgtype_list=['false', 'true']):
    orgres2_descmatch_dists = {}
    for orgtype in orgtype_list:
        printDBG('[rr2] getting orgtype=%r distances between sifts' % orgtype)
        orgres = allres.get_orgtype(orgtype)
        qrids = orgres.qrids
        rids  = orgres.rids
        try:
            adesc1, adesc2 = get_matching_descriptors(allres, qrids, rids)
        except Exception:
            orgres.printme3()
            raise
        printDBG('[rr2]  * adesc1.shape = %r' % (adesc1.shape,))
        printDBG('[rr2]  * adesc2.shape = %r' % (adesc2.shape,))
        #dist_list = ['L1', 'L2', 'hist_isect', 'emd']
        #dist_list = ['L1', 'L2', 'hist_isect']
        dist_list = ['L2', 'hist_isect']
        hist1 = np.asarray(adesc1, dtype=np.float64)
        hist2 = np.asarray(adesc2, dtype=np.float64)
        distances = utool.compute_distances(hist1, hist2, dist_list)
        orgres2_descmatch_dists[orgtype] = distances
    return orgres2_descmatch_dists


def get_matching_descriptors(allres, qrids, rids):
    ibs = allres.ibs
    qdesc_cache = ibsfuncs.get_roi_desc_cache(ibs, qrids)
    rdesc_cache = ibsfuncs.get_roi_desc_cache(ibs, rids)
    desc1_list = []
    desc2_list = []
    for qrid, rid in izip(qrids, rids):
        try:
            fm = get_feat_matches(allres, qrid, rid)
            if len(fm) == 0:
                continue
        except KeyError:
            continue
        desc1_m = qdesc_cache[qrid][fm.T[0]]
        desc2_m = rdesc_cache[rid][fm.T[1]]
        desc1_list.append(desc1_m)
        desc2_list.append(desc2_m)
    aggdesc1 = np.vstack(desc1_list)
    aggdesc2 = np.vstack(desc2_list)
    return aggdesc1, aggdesc2
