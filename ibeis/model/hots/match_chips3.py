from __future__ import absolute_import, division, print_function
import utool
import sys
from ibeis.model.hots import QueryRequest
from ibeis.model.hots import NNIndex
from ibeis.model.hots import matching_functions as mf
(print, print_, printDBG, rrr, profile) = utool.inject(
    __name__, '[mc3]', DEBUG=False)


USE_CACHE = '--nocache-query' not in sys.argv
USE_BIGCACHE = '--nocache-big' not in sys.argv


@utool.indent_func
def quickly_ensure_qreq(ibs, qrids=None, drids=None):
    # This function is purely for hacking, eventually prep request or something
    # new should be good enough to where this doesnt matter
    print(' --- quick ensure qreq --- ')
    ibs._init_query_requestor()
    qreq = ibs.qreq
    query_cfg = ibs.cfg.query_cfg
    rids = ibs.get_recognition_database_rids()
    if qrids is None:
        qrids = rids
    if drids is None:
        drids = rids
    qreq = prep_query_request(qreq=qreq, query_cfg=query_cfg,
                              qrids=qrids, drids=drids)
    pre_exec_checks(ibs, qreq)
    return qreq


#@utool.indent_func('[prep_qreq]')
def prep_query_request(qreq=None, query_cfg=None,
                       qrids=None, drids=None, **kwargs):
    """  Builds or modifies a query request object """
    print(' --- Prep QueryRequest --- ')
    if qreq is None:
        qreq = QueryRequest.QueryRequest()
    if qrids is not None:
        assert len(qrids) > 0, 'cannot query nothing!'
        qreq.qrids = qrids
    if drids is not None:
        assert len(drids) > 0, 'cannot search nothing!'
        qreq.drids = drids
    if query_cfg is None:
        query_cfg = qreq.cfg
    if len(kwargs) > 0:
        query_cfg = query_cfg.deepcopy(**kwargs)
    qreq.set_cfg(query_cfg)
    return qreq


#----------------------
# Query and database checks
#----------------------


#@utool.indent_func('[pre_exec]')
#@profile
def pre_exec_checks(ibs, qreq):
    """ Ensures that the NNIndex's data_index is pointing to the correct
    set of feature descriptors """
    print('  --- Pre Exec ---')
    feat_cfgstr = qreq.cfg._feat_cfg.get_cfgstr()
    drids_hashid = qreq.get_drids_hashid()
    # Ensure the index / inverted index exist for this config
    dftup_hashid = drids_hashid + feat_cfgstr
    if dftup_hashid not in qreq.dftup2_index:
        # Get qreq config information
        drids = qreq.get_internal_drids()
        # Compute the FLANN Index
        data_index = NNIndex.NNIndex(ibs, drids)
        qreq.dftup2_index[dftup_hashid] = data_index
    qreq.data_index = qreq.dftup2_index[dftup_hashid]
    return qreq


#----------------------
# Main Query Logic
#----------------------

# Query Level 2
#@utool.indent_func('[Q2]')
@profile
def process_query_request(ibs, qreq,
                          safe=True,
                          use_cache=USE_CACHE,
                          use_bigcache=USE_BIGCACHE):
    """
    The standard query interface.
    INPUT:
        ibs  - ibeis control object
        qreq - query request object (should be the same as ibs.qreq)
    Checks a big cache for qrid2_qres.
    If cache miss, tries to load each qres individually.
    On an individual cache miss, it preforms the query.
    """
    print(' --- Process QueryRequest --- ')
    if len(qreq.qrids) <= 1:
        # Do not use bigcache single queries
        use_bigcache = False
    # Try and load directly from a big cache
    if use_bigcache:
        bigcache_dpath = qreq.bigcachedir
        bigcache_fname = (ibs.get_dbname() + '_QRESMAP' +
                          qreq.get_qrids_hashid() + qreq.get_drids_hashid())
        bigcache_cfgstr = qreq.cfg.get_cfgstr()
    if use_cache and use_bigcache:
        try:
            qrid2_qres = utool.load_cache(bigcache_dpath,
                                          bigcache_fname,
                                          bigcache_cfgstr)
            print('... qrid2_qres bigcache hit')
            return qrid2_qres
        except IOError:
            print('... qrid2_qres bigcache miss')
    # Try loading as many cached results as possible
    if use_cache:
        qrid2_qres, failed_qrids = mf.try_load_resdict(qreq)
    else:
        qrid2_qres = {}
        failed_qrids = qreq.qrids

    # Execute and save queries
    if len(failed_qrids) > 0:
        if safe:
            qreq = pre_exec_checks(ibs, qreq)
        computed_qrid2_qres = execute_query_and_save_L1(ibs, qreq, failed_qrids)
        qrid2_qres.update(computed_qrid2_qres)  # Update cached results
    if use_bigcache:
        utool.save_cache(bigcache_dpath,
                         bigcache_fname,
                         bigcache_cfgstr, qrid2_qres)
    return qrid2_qres


# Query Level 1
#@utool.indent_func('[Q1]')
#@profile
def execute_query_and_save_L1(ibs, qreq, failed_qrids=[]):
    #print('[q1] execute_query_and_save_L1()')
    orig_qrids = qreq.qrids
    if len(failed_qrids) > 0:
        qreq.qrids = failed_qrids
    qrid2_qres = execute_query_L0(ibs, qreq)  # Execute Queries
    for qrid, res in qrid2_qres.iteritems():  # Cache Save
        res.save(ibs)
    qreq.qrids = orig_qrids
    return qrid2_qres


# Query Level 0
#@utool.indent_func('[Q0]')
#@profile
def execute_query_L0(ibs, qreq):
    """
    Driver logic of query pipeline
    Input:
        ibs   - HotSpotter database object to be queried
        qreq - QueryRequest Object   # use prep_qreq to create one
    Output:
        qrid2_qres - mapping from query indexes to QueryResult Objects
    """
    # Query Chip Indexes
    # * vsone qrids/drids swapping occurs here
    qrids = qreq.get_internal_qrids()

    # Nearest neighbors (qrid2_nns)
    # * query descriptors assigned to database descriptors
    # * FLANN used here
    qrid2_nns = mf.nearest_neighbors(
        ibs, qrids, qreq)

    # Nearest neighbors weighting and scoring (filt2_weights, filt2_meta)
    # * feature matches are weighted
    filt2_weights, filt2_meta = mf.weight_neighbors(
        ibs, qrid2_nns, qreq)

    # Thresholding and weighting (qrid2_nnfilter)
    # * feature matches are pruned
    qrid2_nnfilt = mf.filter_neighbors(
        ibs, qrid2_nns, filt2_weights, qreq)

    # Nearest neighbors to chip matches (qrid2_chipmatch)
    # * Inverted index used to create rid2_fmfsfk (TODO: crid2_fmfv)
    # * Initial scoring occurs
    # * vsone inverse swapping occurs here
    qrid2_chipmatch_FILT = mf.build_chipmatches(
        qrid2_nns, qrid2_nnfilt, qreq)

    # Spatial verification (qrid2_chipmatch) (TODO: cython)
    # * prunes chip results and feature matches
    qrid2_chipmatch_SVER = mf.spatial_verification(
        ibs, qrid2_chipmatch_FILT, qreq, dbginfo=False)

    # Query results format (qrid2_qres) (TODO: SQL / Json Encoding)
    # * Final Scoring. Prunes chip results.
    # * packs into a wrapped query result object
    qrid2_qres = mf.chipmatch_to_resdict(
        ibs, qrid2_chipmatch_SVER, filt2_meta, qreq)

    return qrid2_qres
