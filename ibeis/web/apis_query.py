# -*- coding: utf-8 -*-
"""
Dependencies: flask, tornado
"""
from __future__ import absolute_import, division, print_function, unicode_literals
from ibeis.control import accessor_decors, controller_inject
from ibeis.algo.hots import pipeline
from flask import url_for, request, current_app  # NOQA
from os.path import join, dirname, abspath
import numpy as np   # NOQA
import utool as ut
import vtool as vt
import cv2  # NOQA
import dtool
from ibeis.web import appfuncs as appf


CLASS_INJECT_KEY, register_ibs_method = (
    controller_inject.make_ibs_register_decorator(__name__))
register_api   = controller_inject.get_ibeis_flask_api(__name__)
register_route = controller_inject.get_ibeis_flask_route(__name__)


@register_ibs_method
@accessor_decors.default_decorator
@register_api('/api/query/recognition_query_aids/', methods=['GET'])
def get_recognition_query_aids(ibs, is_known, species=None):
    """
    DEPCIRATE

    RESTful:
        Method: GET
        URL:    /api/query/recognition_query_aids/
    """
    qaid_list = ibs.get_valid_aids(is_known=is_known, species=species)
    return qaid_list


@register_ibs_method
@register_api('/api/query/chips/simple_dict/', methods=['GET'])
def query_chips_simple_dict(ibs, *args, **kwargs):
    r"""
    Runs query_chips, but returns a json compatible dictionary

    Args:
        same as query_chips

    RESTful:
        Method: GET
        URL:    /api/query/chips/simple_dict/

    SeeAlso:
        query_chips

    CommandLine:
        python -m ibeis.web.apis_query --test-query_chips_simple_dict:0
        python -m ibeis.web.apis_query --test-query_chips_simple_dict:1

        python -m ibeis.web.apis_query --test-query_chips_simple_dict:0 --humpbacks

    Example:
        >>> # WEB_DOCTEST
        >>> from ibeis.control.IBEISControl import *  # NOQA
        >>> import ibeis
        >>> ibs = ibeis.opendb(defaultdb='testdb1')
        >>> #qaid = ibs.get_valid_aids()[0:3]
        >>> qaids = ibs.get_valid_aids()
        >>> daids = ibs.get_valid_aids()
        >>> dict_list = ibs.query_chips_simple_dict(qaids, daids)
        >>> qgids = ibs.get_annot_image_rowids(qaids)
        >>> qnids = ibs.get_annot_name_rowids(qaids)
        >>> for dict_, qgid, qnid in zip(dict_list, qgids, qnids):
        >>>     dict_['qgid'] = qgid
        >>>     dict_['qnid'] = qnid
        >>>     dict_['dgid_list'] = ibs.get_annot_image_rowids(dict_['daid_list'])
        >>>     dict_['dnid_list'] = ibs.get_annot_name_rowids(dict_['daid_list'])
        >>>     dict_['dgname_list'] = ibs.get_image_gnames(dict_['dgid_list'])
        >>>     dict_['qgname'] = ibs.get_image_gnames(dict_['qgid'])
        >>> result  = ut.list_str(dict_list, nl=2, precision=2, hack_liststr=True)
        >>> result = result.replace('u\'', '"').replace('\'', '"')
        >>> print(result)

    Example:
        >>> # WEB_DOCTEST
        >>> from ibeis.control.IBEISControl import *  # NOQA
        >>> import time
        >>> import ibeis
        >>> import requests
        >>> # Start up the web instance
        >>> web_instance = ibeis.opendb_in_background(db='testdb1', web=True, browser=False)
        >>> time.sleep(.5)
        >>> baseurl = 'http://127.0.1.1:5000'
        >>> data = dict(qaid_list=[1])
        >>> resp = requests.get(baseurl + '/api/query/chips/simple_dict/', data=data)
        >>> print(resp)
        >>> web_instance.terminate()
        >>> json_dict = resp.json()
        >>> cmdict_list = json_dict['response']
        >>> assert 'score_list' in cmdict_list[0]

    """
    kwargs['return_cm_simple_dict'] = True
    return ibs.query_chips(*args, **kwargs)


@register_ibs_method
@register_api('/api/query/chips/dict/', methods=['GET'])
def query_chips_dict(ibs, *args, **kwargs):
    """
    Runs query_chips, but returns a json compatible dictionary

    RESTful:
        Method: GET
        URL:    /api/query/chips/dict/
    """
    kwargs['return_cm_dict'] = True
    return ibs.query_chips(*args, **kwargs)


@register_api('/api/review/query/graph/', methods=['POST'])
def process_graph_match_html(ibs, **kwargs):
    """
    RESTful:
        Method: POST
        URL:    /api/review/query/graph/
    """
    def sanitize(state):
        state = state.strip().lower()
        state = ''.join(state.split())
        return state
    import uuid
    map_dict = {
        'visuallysame'      : 'matched',
        'visuallydifferent' : 'notmatched',
        'cannottell'        : 'notcomparable',
    }
    annot_uuid_1 = uuid.UUID(request.form['query-match-annot-uuid-1'])
    annot_uuid_2 = uuid.UUID(request.form['query-match-annot-uuid-2'])
    state = request.form.get('query-match-submit', '')
    state = sanitize(state)
    state = map_dict[state]
    assert state in ['matched', 'notmatched', 'notcomparable'], 'matching_state_list has unrecognized states'
    return (annot_uuid_1, annot_uuid_2, state, )


def make_image(aid, cm, qreq_, view_orientation='vertical', draw_matches=True):
    """"
    CommandLine:
        python -m ibeis.web.apis_query make_image --show

    Example:
        >>> # SCRIPT
        >>> from ibeis.web.apis_query import *  # NOQA
        >>> import ibeis
        >>> cm, qreq_ = ibeis.testdata_cm('PZ_MTEST', a='default:dindex=0:10,qindex=0:1')
        >>> aid = cm.get_top_aids()[0]
        >>> image = make_image(aid, cm, qreq_)
        >>> ut.quit_if_noshow()
        >>> import plottool as pt
        >>> pt.imshow(image)
        >>> ut.show_if_requested()
    """
    render_config = {
        'dpi'              : 150,
        'draw_fmatches'    : draw_matches,
        'vert'             : view_orientation == 'vertical',
        'show_aidstr'      : False,
        'show_name'        : False,
        'show_exemplar'    : False,
        'show_num_gt'      : False,
        'show_timedelta'   : False,
        'show_name_rank'   : False,
        'show_score'       : False,
        'show_annot_score' : False,
        'show_name_score'  : False,
        'draw_lbl'         : False,
        'draw_border'      : False,
    }
    image = cm.render_single_annotmatch(qreq_, aid, **render_config)
    image = vt.crop_out_imgfill(image, fillval=(255, 255, 255), thresh=64)
    return image


@register_api('/api/review/query/graph/', methods=['GET'])
def review_graph_match_html(ibs, review_pair, cm_dict, query_config_dict, _internal_state, callback_url,
                            callback_method='POST', view_orientation='vertical',
                            include_jquery=False):
    from ibeis.algo.hots.chip_match import ChipMatch
    # from ibeis.algo.hots.query_request import QueryRequest

    view_orientation = view_orientation.lower()
    if view_orientation not in ['vertical', 'horizontal']:
        view_orientation = 'horizontal'

    annot_uuid_1 = review_pair['annot_uuid_1']
    aid_1 = ibs.get_annot_aids_from_uuid(annot_uuid_1)
    annot_uuid_2 = review_pair['annot_uuid_2']
    aid_2 = ibs.get_annot_aids_from_uuid(annot_uuid_2)
    cm_dict['qaid'] = ibs.get_annot_aids_from_uuid(cm_dict['qannot_uuid'])
    cm_dict['qnid'] = ibs.get_name_rowids_from_uuid(cm_dict['qname_uuid'], nid_hack=True)
    cm_dict['daid_list'] = ibs.get_annot_aids_from_uuid(cm_dict['dannot_uuid_list'])
    cm_dict['dnid_list'] = ibs.get_name_rowids_from_uuid(cm_dict['dname_uuid_list'], nid_hack=True)
    cm_dict['unique_nids'] = ibs.get_name_rowids_from_uuid(cm_dict['unique_name_uuid_list'], nid_hack=True)

    # print('review_pair = %r' % (review_pair, ))
    # print('cm_dict = %r' % (cm_dict, ))
    # print('query_config_dict = %r' % (query_config_dict, ))
    # print('_internal_state = %r' % (_internal_state, ))

    cm = ChipMatch.from_dict(cm_dict)
    qreq_ = ibs.new_query_request([aid_1], [aid_2],
                                  cfgdict=query_config_dict)

    image_matches_src = appf.embed_image_html(make_image(aid_2, cm, qreq_,
                                                         view_orientation=view_orientation))
    image_clean_src = appf.embed_image_html(make_image(aid_2, cm, qreq_,
                                                       view_orientation=view_orientation,
                                                       draw_matches=False))

    root_path = dirname(abspath(__file__))
    css_file_list = [
        ['css', 'style.css'],
        ['include', 'bootstrap', 'css', 'bootstrap.css'],
    ]
    json_file_list = [
        ['javascript', 'script.js'],
        ['include', 'bootstrap', 'js', 'bootstrap.js'],
    ]

    if include_jquery:
        json_file_list = [
            ['javascript', 'jquery.min.js'],
        ] + json_file_list

    EMBEDDED_CSS = ''
    EMBEDDED_JAVASCRIPT = ''

    css_template_fmtstr = '<style type="text/css" ia-dependency="css">%s</style>\n'
    json_template_fmtstr = '<script type="text/javascript" ia-dependency="javascript">%s</script>\n'
    for css_file in css_file_list:
        css_filepath_list = [root_path, 'static'] + css_file
        with open(join(*css_filepath_list)) as css_file:
            EMBEDDED_CSS += css_template_fmtstr % (css_file.read(), )

    for json_file in json_file_list:
        json_filepath_list = [root_path, 'static'] + json_file
        with open(join(*json_filepath_list)) as json_file:
            EMBEDDED_JAVASCRIPT += json_template_fmtstr % (json_file.read(), )

    return appf.template('turk', 'query_match_insert',
                         image_clean_src=image_clean_src,
                         image_matches_src=image_matches_src,
                         annot_uuid_1=str(annot_uuid_1),
                         annot_uuid_2=str(annot_uuid_2),
                         view_orientation=view_orientation,
                         callback_url=callback_url,
                         callback_method=callback_method,
                         EMBEDDED_CSS=EMBEDDED_CSS,
                         EMBEDDED_JAVASCRIPT=EMBEDDED_JAVASCRIPT)


@register_route('/test/review/query/chips/', methods=['GET'])
def review_query_chips_test():
    ibs = current_app.ibs
    result_dict = ibs.query_chips_test()

    review_pair = result_dict['inference_dict']['annot_pair_dict']['review_pair_list'][0]
    annot_uuid_key = str(review_pair['annot_uuid_key'])
    cm_dict = result_dict['cm_dict'][annot_uuid_key]
    query_config_dict = result_dict['query_config_dict']
    _internal_state = result_dict['inference_dict']['_internal_state']
    callback_url = request.args.get('callback_url', url_for('process_graph_match_html'))
    callback_method = request.args.get('callback_method', 'POST')
    # view_orientation = request.args.get('view_orientation', 'vertical')
    view_orientation = request.args.get('view_orientation', 'horizontal')

    template_html = review_graph_match_html(ibs, review_pair, cm_dict, query_config_dict, _internal_state, callback_url, callback_method, view_orientation, include_jquery=True)
    template_html = '''
        <script src="http://code.jquery.com/jquery-2.2.1.min.js" ia-dependency="javascript"></script>
        %s
    ''' % (template_html, )
    return template_html
    return 'done'


@register_ibs_method
@register_api('/test/query/chips/', methods=['GET'])
def query_chips_test(ibs, **kwargs):
    """
    CommandLine:
        python -m ibeis.web.apis_query query_chips_test

    Example:
        >>> # SLOW_DOCTEST
        >>> from ibeis.control.IBEISControl import *  # NOQA
        >>> import ibeis
        >>> qreq_ = ibeis.testdata_qreq_()
        >>> ibs = qreq_.ibs
        >>> result_dict = ibs.query_chips_test()
        >>> print(result_dict)
    """
    from random import shuffle  # NOQA
    # Compile test data
    aid_list = ibs.get_valid_aids()
    shuffle(aid_list)
    qaid_list = aid_list[:3]
    daid_list = aid_list[-10:]
    result_dict = ibs.query_chips_graph(qaid_list, daid_list, **kwargs)
    return result_dict


@register_ibs_method
@register_api('/api/query/graph/', methods=['GET'])
def query_chips_graph(ibs, qaid_list, daid_list, user_feedback=None, query_config_dict={}, echo_query_params=True):
    from ibeis.algo.hots.chip_match import AnnotInference
    import uuid

    def convert_to_uuid(nid):
        try:
            text = ibs.get_name_texts(nid)
            uuid_ = uuid.UUID(text)
        except ValueError:
            uuid_ = nid
        return uuid_

    cm_list, qreq_ = ibs.query_chips(qaid_list=qaid_list, daid_list=daid_list,
                                     cfgdict=query_config_dict, return_request=True)
    cm_dict = {
        str(ibs.get_annot_uuids(cm.qaid)): {
            # 'qaid'                  : cm.qaid,
            'qannot_uuid'           : ibs.get_annot_uuids(cm.qaid),
            # 'qnid'                  : cm.qnid,
            'qname_uuid'            : convert_to_uuid(cm.qnid),
            # 'daid_list'             : cm.daid_list,
            'dannot_uuid_list'      : ibs.get_annot_uuids(cm.daid_list),
            # 'dnid_list'             : cm.dnid_list,
            'dname_uuid_list'       : [convert_to_uuid(nid) for nid in cm.dnid_list],
            'score_list'            : cm.score_list,
            'annot_score_list'      : cm.annot_score_list,
            'fm_list'               : cm.fm_list,
            'fsv_list'              : cm.fsv_list,
            # Non-corresponding lists to above
            # 'unique_nids'         : cm.unique_nids,
            'unique_name_uuid_list' : [convert_to_uuid(nid) for nid in cm.unique_nids],
            'name_score_list'       : cm.name_score_list,
            # Placeholders for the reinitialization of the ChipMatch object
            'fk_list'               : None,
            'H_list'                : None,
            'fsv_col_lbls'          : None,
            'filtnorm_aids'         : None,
            'filtnorm_fxs'          : None,
        }
        for cm in cm_list
    }
    annot_inference = AnnotInference(qreq_, cm_list, user_feedback)
    inference_dict = annot_inference.make_annot_inference_dict()
    result_dict = {
        'cm_dict'        : cm_dict,
        'inference_dict' : inference_dict,
    }
    if echo_query_params:
        result_dict['query_annot_uuid_list'] = ibs.get_annot_uuids(qaid_list)
        result_dict['database_annot_uuid_list'] = ibs.get_annot_uuids(daid_list)
        result_dict['query_config_dict'] = query_config_dict
    return result_dict


@register_ibs_method
@register_api('/api/query/chips/', methods=['GET'])
def query_chips(ibs, qaid_list=None,
                daid_list=None,
                cfgdict=None,
                use_cache=None,
                use_bigcache=None,
                qreq_=None,
                return_request=False,
                verbose=pipeline.VERB_PIPELINE,
                save_qcache=None,
                prog_hook=None,
                return_cm_dict=False,
                return_cm_simple_dict=False,
                ):
    r"""
    Submits a query request to the hotspotter recognition pipeline. Returns
    a list of QueryResult objects.

    Args:
        qaid_list (list): a list of annotation ids to be submitted as
            queries
        daid_list (list): a list of annotation ids used as the database
            that will be searched
        cfgdict (dict): dictionary of configuration options used to create
            a new QueryRequest if not already specified
        use_cache (bool): turns on/off chip match cache (default: True)
        use_bigcache (bool): turns one/off chunked chip match cache (default:
            True)
        qreq_ (QueryRequest): optional, a QueryRequest object that
            overrides all previous settings
        return_request (bool): returns the request which will be created if
            one is not already specified
        verbose (bool): default=False, turns on verbose printing

    Returns:
        list: a list of ChipMatch objects containing the matching
            annotations, scores, and feature matches

    Returns(2):
        tuple: (cm_list, qreq_) - a list of query results and optionally the
            QueryRequest object used

    RESTful:
        Method: PUT
        URL:    /api/query/chips/

    CommandLine:
        python -m ibeis.web.apis_query --test-query_chips

        # Test speed of single query
        python -m ibeis --tf IBEISController.query_chips --db PZ_Master1 \
            -a default:qindex=0:1,dindex=0:500 --nocache-hs

        python -m ibeis --tf IBEISController.query_chips --db PZ_Master1 \
            -a default:qindex=0:1,dindex=0:3000 --nocache-hs

        python -m ibeis.web.apis_query --test-query_chips:1 --show
        python -m ibeis.web.apis_query --test-query_chips:2 --show

    Example:
        >>> # SLOW_DOCTEST
        >>> from ibeis.control.IBEISControl import *  # NOQA
        >>> import ibeis
        >>> qreq_ = ibeis.testdata_qreq_()
        >>> ibs = qreq_.ibs
        >>> cm_list = qreq_.execute()
        >>> cm = cm_list[0]
        >>> ut.quit_if_noshow()
        >>> cm.ishow_analysis(qreq_)
        >>> ut.show_if_requested()

    Example:
        >>> # SLOW_DOCTEST
        >>> #from ibeis.all_imports import *  # NOQA
        >>> import ibeis
        >>> from ibeis.control.IBEISControl import *  # NOQA
        >>> qaid_list = [1]
        >>> daid_list = [1, 2, 3, 4, 5]
        >>> ibs = ibeis.test_main(db='testdb1')
        >>> qreq_ = ibs.new_query_request(qaid_list, daid_list)
        >>> cm = ibs.query_chips(qaid_list, daid_list, use_cache=False, qreq_=qreq_)[0]
        >>> ut.quit_if_noshow()
        >>> cm.ishow_analysis(qreq_)
        >>> ut.show_if_requested()

    Example1:
        >>> # SLOW_DOCTEST
        >>> #from ibeis.all_imports import *  # NOQA
        >>> import ibeis
        >>> from ibeis.control.IBEISControl import *  # NOQA
        >>> qaid_list = [1]
        >>> daid_list = [1, 2, 3, 4, 5]
        >>> ibs = ibeis.test_main(db='testdb1')
        >>> cfgdict = {'pipeline_root':'BC_DTW'}
        >>> qreq_ = ibs.new_query_request(qaid_list, daid_list, cfgdict=cfgdict, verbose=True)
        >>> cm = ibs.query_chips(qaid_list, daid_list, use_cache=False, qreq_=qreq_)[0]
        >>> ut.quit_if_noshow()
        >>> cm.ishow_analysis(qreq_)
        >>> ut.show_if_requested()
    """
    from ibeis.algo.hots import match_chips4 as mc4
    # The qaid and daid objects are allowed to be None if qreq_ is
    # specified

    if qaid_list is None:
        qaid_list = qreq_.qaids
    if daid_list is None:
        if qreq_ is not None:
            daid_list = qreq_.daids
        else:
            daid_list = ibs.get_valid_aids()

    qaid_list, was_scalar = ut.wrap_iterable(qaid_list)

    # Check fo empty queries
    try:
        assert len(daid_list) > 0, 'there are no database chips'
        assert len(qaid_list) > 0, 'there are no query chips'
    except AssertionError as ex:
        ut.printex(ex, 'Impossible query request', iswarning=True,
                   keys=['qaid_list', 'daid_list'])
        if ut.SUPER_STRICT:
            raise
        cm_list = [None for qaid in qaid_list]
    else:
        # Check for consistency
        if qreq_ is not None:
            ut.assert_lists_eq(
                qreq_.qaids, qaid_list,
                'qaids do not agree with qreq_', verbose=True)
            ut.assert_lists_eq(
                qreq_.daids, daid_list,
                'daids do not agree with qreq_', verbose=True)
        if qreq_ is None:
            qreq_ = ibs.new_query_request(qaid_list, daid_list,
                                          cfgdict=cfgdict, verbose=verbose)

        if isinstance(qreq_, dtool.BaseRequest):
            # Dtool has a new-ish way of doing requests.  Eventually requests
            # will be depricated and all of this will go away though.
            cm_list = qreq_.execute()
        else:
            # Send query to hotspotter (runs the query)
            cm_list = mc4.submit_query_request(
                ibs,  qaid_list, daid_list, use_cache, use_bigcache,
                cfgdict=cfgdict, qreq_=qreq_,
                verbose=verbose, save_qcache=save_qcache, prog_hook=prog_hook)

    if return_cm_dict or return_cm_simple_dict:
        # Convert to cm_list
        if return_cm_simple_dict:
            for cm in cm_list:
                cm.qauuid = ibs.get_annot_uuids(cm.qaid)
                cm.dauuid_list = ibs.get_annot_uuids(cm.daid_list)
            keys = ['qauuid', 'dauuid_list']
            cm_list = [cm.as_simple_dict(keys) for cm in cm_list]
        elif return_cm_dict:
            cm_list = [cm.as_dict() for cm in cm_list]

    if was_scalar:
        # hack for scalar input
        assert len(cm_list) == 1
        cm_list = cm_list[0]

    if return_request:
        return cm_list, qreq_
    else:
        return cm_list


if __name__ == '__main__':
    """
    CommandLine:
        python -m ibeis.web.app
        python -m ibeis.web.app --allexamples
        python -m ibeis.web.app --allexamples --noface --nosrc
    """
    import multiprocessing
    multiprocessing.freeze_support()  # for win32
    import utool as ut  # NOQA
    ut.doctest_funcs()
