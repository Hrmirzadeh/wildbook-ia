# -*- coding: utf-8 -*-
"""
Dependencies: flask, tornado

SeeAlso:
    routes.turk_identification
"""
from __future__ import absolute_import, division, print_function, unicode_literals
from ibeis.control import accessor_decors, controller_inject
from ibeis.algo.hots import pipeline
from flask import url_for, request, current_app  # NOQA
from os.path import join, dirname, abspath, exists
import cv2
import numpy as np   # NOQA
import utool as ut
from ibeis.web import appfuncs as appf
import traceback
from ibeis import constants as const
import six
ut.noinject('[apis_query]')


CLASS_INJECT_KEY, register_ibs_method = (
    controller_inject.make_ibs_register_decorator(__name__))
register_api   = controller_inject.get_ibeis_flask_api(__name__)
register_route = controller_inject.get_ibeis_flask_route(__name__)


ANNOT_INFR_PEAK_MAX = 50


@register_ibs_method
@accessor_decors.default_decorator
@register_api('/api/query/annot/rowid/', methods=['GET'])
def get_recognition_query_aids(ibs, is_known, species=None):
    """
    DEPCIRATE

    RESTful:
        Method: GET
        URL:    /api/query/annot/rowid/
    """
    qaid_list = ibs.get_valid_aids(is_known=is_known, species=species)
    return qaid_list


@register_ibs_method
@register_api('/api/query/chip/dict/simple/', methods=['GET'])
def query_chips_simple_dict(ibs, *args, **kwargs):
    r"""
    Runs query_chips, but returns a json compatible dictionary

    Args:
        same as query_chips

    RESTful:
        Method: GET
        URL:    /api/query/chip/dict/simple/

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
        >>> result  = ut.repr2(dict_list, nl=2, precision=2, hack_liststr=True)
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
        >>> time.sleep(10)
        >>> web_port = ibs.get_web_port_via_scan()
        >>> if web_port is None:
        >>>     raise ValueError('IA web server is not running on any expected port')
        >>> baseurl = 'http://127.0.1.1:%s' % (web_port, )
        >>> data = dict(qaid_list=[1])
        >>> resp = requests.get(baseurl + '/api/query/chip/simple/dict/', data=data)
        >>> print(resp)
        >>> web_instance.terminate()
        >>> json_dict = resp.json()
        >>> cmdict_list = json_dict['response']
        >>> assert 'score_list' in cmdict_list[0]

    """
    kwargs['return_cm_simple_dict'] = True
    return ibs.query_chips(*args, **kwargs)


@register_ibs_method
@register_api('/api/query/chip/dict/', methods=['GET'])
def query_chips_dict(ibs, *args, **kwargs):
    """
    Runs query_chips, but returns a json compatible dictionary

    RESTful:
        Method: GET
        URL:    /api/query/chip/dict/
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
        'sameanimal'       : const.REVIEW.POSITIVE,
        'differentanimals' : const.REVIEW.NEGATIVE,
        'cannottell'       : const.REVIEW.INCOMPARABLE,
        'unreviewed'       : const.REVIEW.UNREVIEWED,
        'unknown'          : const.REVIEW.UNKNOWN,
        'photobomb'        : 'photobomb',
        'scenerymatch'     : 'scenerymatch',
    }
    annot_uuid_1 = uuid.UUID(request.form['identification-annot-uuid-1'])
    annot_uuid_2 = uuid.UUID(request.form['identification-annot-uuid-2'])
    state = request.form.get('identification-submit', '')
    state = sanitize(state)
    state = map_dict[state]
    tag_list = []
    if state in ['photobomb', 'scenerymatch']:
        tag_list.append(state)
        state = const.REVIEW.NEGATIVE
    assert state in map_dict.values(), 'matching state is unrecognized'
    # Get checbox tags
    checbox_tag_list = ['photobomb', 'scenerymatch']
    for checbox_tag in checbox_tag_list:
        checkbox_name = 'ia-%s-value' % (checbox_tag)
        if checkbox_name in request.form:
            tag_list.append(checbox_tag)
    tag_list = sorted(set(tag_list))
    if len(tag_list) == 0:
        tag_list = None
    tag_str = ';'.join(tag_list)
    return (annot_uuid_1, annot_uuid_2, state, tag_str, 'web-wb', 1.0)


@register_api('/api/review/query/graph/v2/', methods=['POST'])
def process_graph_match_html_v2(ibs, query_uuid, **kwargs):
    query_annot_infr, _ = ibs.get_query_annot_infr_query_chips_graph_v2(query_uuid)
    response_tuple = ibs.process_graph_match_html(**kwargs)
    annot_uuid_1, annot_uuid_2, decision, tags, user_id, confidence = response_tuple
    aid1 = ibs.get_annot_aids_from_uuid(annot_uuid_1)
    aid2 = ibs.get_annot_aids_from_uuid(annot_uuid_2)
    edge = (aid1, aid2, )
    query_annot_infr.add_feedback(edge, decision, tags=tags, user_id=user_id,
                                  confidence=confidence)
    query_annot_infr.write_ibeis_staging_feedback()
    return response_tuple


def ensure_review_image(ibs, aid, cm, qreq_, view_orientation='vertical',
                        draw_matches=True, verbose=False):
    r""""
    Create the review image for a pair of annotations

    CommandLine:
        python -m ibeis.web.apis_query ensure_review_image --show

    Example:
        >>> # SCRIPT
        >>> from ibeis.web.apis_query import *  # NOQA
        >>> import ibeis
        >>> cm, qreq_ = ibeis.testdata_cm('PZ_MTEST', a='default:dindex=0:10,qindex=0:1')
        >>> ibs = qreq_.ibs
        >>> aid = cm.get_top_aids()[0]
        >>> tt = ut.tic('make image')
        >>> image = ensure_review_image(ibs, aid, cm, qreq_)
        >>> ut.toc(tt)
        >>> ut.quit_if_noshow()
        >>> print('image.shape = %r' % (image.shape,))
        >>> print('image.dtype = %r' % (image.dtype,))
        >>> ut.print_object_size(image)
        >>> import plottool as pt
        >>> pt.imshow(image)
        >>> ut.show_if_requested()
    """
    from ibeis.gui import id_review_api
    # Get thumb path
    match_thumb_path = ibs.get_match_thumbdir()
    match_thumb_filename = id_review_api.get_match_thumb_fname(cm, aid, qreq_,
                                                               view_orientation=view_orientation,
                                                               draw_matches=draw_matches)
    match_thumb_filepath = join(match_thumb_path, match_thumb_filename)
    if verbose:
        print('Checking: %r' % (match_thumb_filepath, ))

    if exists(match_thumb_filepath):
        image = cv2.imread(match_thumb_filepath)
    else:
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

        if hasattr(qreq_, 'render_single_result'):
            image = qreq_.render_single_result(cm, aid, **render_config)
        else:
            image = cm.render_single_annotmatch(qreq_, aid, **render_config)
        #image = vt.crop_out_imgfill(image, fillval=(255, 255, 255), thresh=64)
        cv2.imwrite(match_thumb_filepath, image)
    return image


@register_api('/api/review/query/graph/', methods=['GET'])
def review_graph_match_html(ibs, review_pair, cm_dict, query_config_dict,
                            _internal_state, callback_url,
                            callback_method='POST',
                            view_orientation='vertical', include_jquery=False):
    r"""
    Args:
        ibs (ibeis.IBEISController):  image analysis api
        review_pair (dict): pair of annot uuids
        cm_dict (dict):
        query_config_dict (dict):
        _internal_state (?):
        callback_url (str):
        callback_method (unicode): (default = u'POST')
        view_orientation (unicode): (default = u'vertical')
        include_jquery (bool): (default = False)

    CommandLine:
        python -m ibeis.web.apis_query review_graph_match_html --show

        ibeis --web
        python -m ibeis.web.apis_query review_graph_match_html --show --domain=localhost

    Example:
        >>> # WEB_DOCTEST
        >>> from ibeis.web.apis_query import *  # NOQA
        >>> import ibeis
        >>> web_ibs = ibeis.opendb_bg_web('testdb1')  # , domain='http://52.33.105.88')
        >>> aids = web_ibs.send_ibeis_request('/api/annot/', 'get')[0:2]
        >>> uuid_list = web_ibs.send_ibeis_request('/api/annot/uuid/', type_='get', aid_list=aids)
        >>> quuid_list = uuid_list[0:1]
        >>> duuid_list = uuid_list
        >>> query_config_dict = {
        >>>    # 'pipeline_root' : 'BC_DTW'
        >>> }
        >>> data = dict(
        >>>     query_annot_uuid_list=quuid_list, database_annot_uuid_list=duuid_list,
        >>>     query_config_dict=query_config_dict,
        >>> )
        >>> jobid = web_ibs.send_ibeis_request('/api/engine/query/graph/', **data)
        >>> print('jobid = %r' % (jobid,))
        >>> status_response = web_ibs.wait_for_results(jobid)
        >>> result_response = web_ibs.read_engine_results(jobid)
        >>> inference_result = result_response['json_result']
        >>> print('inference_result = %r' % (inference_result,))
        >>> auuid2_cm = inference_result['cm_dict']
        >>> quuid = quuid_list[0]
        >>> class_dict = auuid2_cm[str(quuid)]
        >>> # Get information in frontend
        >>> #ibs = ibeis.opendb('testdb1')
        >>> #cm = match_obj = ibeis.ChipMatch.from_dict(class_dict, ibs=ibs)
        >>> #match_obj.print_rawinfostr()
        >>> # Make the dictionary a bit more managable
        >>> #match_obj.compress_top_feature_matches(num=2)
        >>> #class_dict = match_obj.to_dict(ibs=ibs)
        >>> cm_dict = class_dict
        >>> # Package for review
        >>> review_pair = {'annot_uuid_1': quuid, 'annot_uuid_2': duuid_list[1]}
        >>> callback_method = u'POST'
        >>> view_orientation = u'vertical'
        >>> include_jquery = False
        >>> kw = dict(
        >>>     review_pair=review_pair,
        >>>     cm_dict=cm_dict,
        >>>     query_config_dict=query_config_dict,
        >>>     _internal_state=None,
        >>>     callback_url = None,
        >>> )
        >>> html_str = web_ibs.send_ibeis_request('/api/review/query/graph/', type_='get', **kw)
        >>> web_ibs.terminate2()
        >>> ut.quit_if_noshow()
        >>> import plottool as pt
        >>> ut.render_html(html_str)
        >>> ut.show_if_requested()

    Example2:
        >>> # DISABLE_DOCTEST
        >>> # This starts off using web to get information, but finishes the rest in python
        >>> from ibeis.web.apis_query import *  # NOQA
        >>> import ibeis
        >>> ut.exec_funckw(review_graph_match_html, globals())
        >>> web_ibs = ibeis.opendb_bg_web('testdb1')  # , domain='http://52.33.105.88')
        >>> aids = web_ibs.send_ibeis_request('/api/annot/', 'get')[0:2]
        >>> uuid_list = web_ibs.send_ibeis_request('/api/annot/uuid/', type_='get', aid_list=aids)
        >>> quuid_list = uuid_list[0:1]
        >>> duuid_list = uuid_list
        >>> query_config_dict = {
        >>>    # 'pipeline_root' : 'BC_DTW'
        >>> }
        >>> data = dict(
        >>>     query_annot_uuid_list=quuid_list, database_annot_uuid_list=duuid_list,
        >>>     query_config_dict=query_config_dict,
        >>> )
        >>> jobid = web_ibs.send_ibeis_request('/api/engine/query/graph/', **data)
        >>> status_response = web_ibs.wait_for_results(jobid)
        >>> result_response = web_ibs.read_engine_results(jobid)
        >>> web_ibs.terminate2()
        >>> # NOW WORK IN THE FRONTEND
        >>> inference_result = result_response['json_result']
        >>> auuid2_cm = inference_result['cm_dict']
        >>> quuid = quuid_list[0]
        >>> class_dict = auuid2_cm[str(quuid)]
        >>> # Get information in frontend
        >>> ibs = ibeis.opendb('testdb1')
        >>> cm = ibeis.ChipMatch.from_dict(class_dict, ibs=ibs)
        >>> cm.print_rawinfostr()
        >>> # Make the dictionary a bit more managable
        >>> cm.compress_top_feature_matches(num=1)
        >>> cm.print_rawinfostr()
        >>> class_dict = cm.to_dict(ibs=ibs)
        >>> cm_dict = class_dict
        >>> # Package for review ( CANT CALL DIRECTLY BECAUSE OF OUT OF CONTEXT )
        >>> review_pair = {'annot_uuid_1': quuid, 'annot_uuid_2': duuid_list[1]}
        >>> x = review_graph_match_html(ibs, review_pair, cm_dict,
        >>>                             query_config_dict, _internal_state=None,
        >>>                             callback_url=None)
        >>> ut.quit_if_noshow()
        >>> import plottool as pt
        >>> ut.render_html(html_str)
        >>> ut.show_if_requested()
    """
    from ibeis.algo.hots import chip_match
    # from ibeis.algo.hots.query_request import QueryRequest

    proot = query_config_dict.get('pipeline_root', 'vsmany')
    proot = query_config_dict.get('proot', proot)
    if proot.upper() in ('BC_DTW', 'OC_WDTW'):
        cls = chip_match.AnnotMatch  # ibs.depc_annot.requestclass_dict['BC_DTW']
    else:
        cls = chip_match.ChipMatch

    view_orientation = view_orientation.lower()
    if view_orientation not in ['vertical', 'horizontal']:
        view_orientation = 'horizontal'

    # unpack info
    try:
        annot_uuid_1 = review_pair['annot_uuid_1']
        annot_uuid_2 = review_pair['annot_uuid_2']
    except Exception:
        #??? HACK
        # FIXME:
        print('[!!!!] review_pair = %r' % (review_pair,))
        review_pair = review_pair[0]
        annot_uuid_1 = review_pair['annot_uuid_1']
        annot_uuid_2 = review_pair['annot_uuid_2']

    ibs.web_check_uuids(qannot_uuid_list=[annot_uuid_1],
                        dannot_uuid_list=[annot_uuid_2])

    aid_1 = ibs.get_annot_aids_from_uuid(annot_uuid_1)
    aid_2 = ibs.get_annot_aids_from_uuid(annot_uuid_2)

    cm = cls.from_dict(cm_dict, ibs=ibs)
    qreq_ = ibs.new_query_request([aid_1], [aid_2],
                                  cfgdict=query_config_dict)

    # Get score
    idx = cm.daid2_idx[aid_2]
    match_score = cm.name_score_list[idx]
    #match_score = cm.aid2_score[aid_2]

    try:
        image_matches = ensure_review_image(ibs, aid_2, cm, qreq_,
                                            view_orientation=view_orientation)
    except KeyError:
        image_matches = np.zeros((100, 100, 3), dtype=np.uint8)
        traceback.print_exc()
    try:
        image_clean = ensure_review_image(ibs, aid_2, cm, qreq_,
                                          view_orientation=view_orientation,
                                          draw_matches=False)
    except KeyError:
        image_clean = np.zeros((100, 100, 3), dtype=np.uint8)
        traceback.print_exc()

    image_matches_src = appf.embed_image_html(image_matches)
    image_clean_src = appf.embed_image_html(image_clean)

    if False:
        from ibeis.web import apis_query
        root_path = dirname(abspath(apis_query.__file__))
    else:
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

    return appf.template('turk', 'identification_insert',
                         match_score=match_score,
                         image_clean_src=image_clean_src,
                         image_matches_src=image_matches_src,
                         annot_uuid_1=str(annot_uuid_1),
                         annot_uuid_2=str(annot_uuid_2),
                         view_orientation=view_orientation,
                         callback_url=callback_url,
                         callback_method=callback_method,
                         EMBEDDED_CSS=EMBEDDED_CSS,
                         EMBEDDED_JAVASCRIPT=EMBEDDED_JAVASCRIPT)


@register_api('/api/review/query/graph/v2/', methods=['GET'])
def review_graph_match_html_v2(ibs, query_uuid, callback_url,
                               callback_method='POST',
                               view_orientation='vertical',
                               include_jquery=False):
    import random
    # from ibeis.algo.hots.query_request import QueryRequest

    ut.embed()

    query_annot_infr, _ = ibs.get_query_annot_infr_query_chips_graph_v2(query_uuid)
    peak_list = query_annot_infr._peek_many(ANNOT_INFR_PEAK_MAX)

    if len(peak_list) == 0:
        raise controller_inject.WebNextReviewExhaustedException(query_uuid)
    peak_index = random.randint(0, len(peak_list) - 1)
    edge, priority = peak_list[peak_index]
    args = (edge, priority, peak_index, len(peak_list) - 1)
    print('Selected edge %r with priority %0.02f out of the peak_list %d / %d' % args)

    # Get score
    aid_1, aid_2 = edge
    cm, aid_1, aid_2 = query_annot_infr.lookup_cm(aid_1, aid_2)
    idx = cm.daid2_idx[aid_2]
    match_score = cm.name_score_list[idx]
    #match_score = cm.aid2_score[aid_2]

    annot_uuid_1 = ibs.get_annot_uuids(aid_1)
    annot_uuid_2 = ibs.get_annot_uuids(aid_2)

    try:
        image_matches = ensure_review_image(ibs, aid_2, cm, query_annot_infr.qreq_,
                                            view_orientation=view_orientation)
    except KeyError:
        image_matches = np.zeros((100, 100, 3), dtype=np.uint8)
        traceback.print_exc()
    try:
        image_clean = ensure_review_image(ibs, aid_2, cm, query_annot_infr.qreq_,
                                          view_orientation=view_orientation,
                                          draw_matches=False)
    except KeyError:
        image_clean = np.zeros((100, 100, 3), dtype=np.uint8)
        traceback.print_exc()

    image_matches_src = appf.embed_image_html(image_matches)
    image_clean_src = appf.embed_image_html(image_clean)

    if False:
        from ibeis.web import apis_query
        root_path = dirname(abspath(apis_query.__file__))
    else:
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

    return appf.template('turk', 'identification_insert',
                         match_score=match_score,
                         image_clean_src=image_clean_src,
                         image_matches_src=image_matches_src,
                         annot_uuid_1=str(annot_uuid_1),
                         annot_uuid_2=str(annot_uuid_2),
                         view_orientation=view_orientation,
                         callback_url=callback_url,
                         callback_method=callback_method,
                         EMBEDDED_CSS=EMBEDDED_CSS,
                         EMBEDDED_JAVASCRIPT=EMBEDDED_JAVASCRIPT)


@register_route('/test/review/query/chip/', methods=['GET'])
def review_query_chips_test(**kwargs):
    """
    CommandLine:
        python -m ibeis.web.apis_query review_query_chips_test --show

    Example:
        >>> # SCRIPT
        >>> import ibeis
        >>> web_ibs = ibeis.opendb_bg_web(
        >>>     browser=True, url_suffix='/test/review/query/chip/?__format__=true')
    """
    ibs = current_app.ibs

    # the old block curvature dtw
    if 'use_bc_dtw' in request.args:
        query_config_dict = {
            'pipeline_root' : 'BC_DTW'
        }
    # the new oriented curvature dtw
    elif 'use_oc_wdtw' in request.args:
        query_config_dict = {
            'pipeline_root' : 'OC_WDTW'
        }
    else:
        query_config_dict = {}
    result_dict = ibs.query_chips_test(query_config_dict=query_config_dict)

    review_pair = result_dict['inference_dict']['annot_pair_dict']['review_pair_list'][0]
    annot_uuid_key = str(review_pair['annot_uuid_key'])
    cm_dict = result_dict['cm_dict'][annot_uuid_key]
    query_config_dict = result_dict['query_config_dict']
    _internal_state = result_dict['inference_dict']['_internal_state']
    callback_url = request.args.get('callback_url', url_for('process_graph_match_html'))
    callback_method = request.args.get('callback_method', 'POST')
    # view_orientation = request.args.get('view_orientation', 'vertical')
    view_orientation = request.args.get('view_orientation', 'horizontal')

    template_html = review_graph_match_html(ibs, review_pair, cm_dict,
                                            query_config_dict, _internal_state,
                                            callback_url, callback_method,
                                            view_orientation,
                                            include_jquery=True)
    template_html = '''
        <script src="http://code.jquery.com/jquery-2.2.1.min.js" ia-dependency="javascript"></script>
        %s
    ''' % (template_html, )
    return template_html
    return 'done'


@register_ibs_method
@register_api('/test/query/chip/', methods=['GET'])
def query_chips_test(ibs, **kwargs):
    """
    CommandLine:
        python -m ibeis.web.apis_query query_chips_test

    Example:
        >>> # SLOW_DOCTEST
        >>> from ibeis.control.IBEISControl import *  # NOQA
        >>> import ibeis
        >>> qreq_ = ibeis.testdata_qreq_(defaultdb='testdb1')
        >>> ibs = qreq_.ibs
        >>> result_dict = ibs.query_chips_test()
        >>> print(result_dict)
    """
    from random import shuffle  # NOQA
    # Compile test data
    aid_list = ibs.get_valid_aids()
    # shuffle(aid_list)
    qaid_list = aid_list[:1]
    daid_list = aid_list[-4:]
    result_dict = ibs.query_chips_graph(qaid_list, daid_list, **kwargs)
    return result_dict


@register_ibs_method
@register_api('/api/query/graph/', methods=['GET', 'POST'])
def query_chips_graph(ibs, qaid_list, daid_list, user_feedback=None,
                      query_config_dict={}, echo_query_params=True):
    from ibeis.algo.hots.orig_graph_iden import OrigAnnotInference
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
            'qname'                 : ibs.get_name_texts(cm.qnid),
            # 'daid_list'             : cm.daid_list,
            'dannot_uuid_list'      : ibs.get_annot_uuids(cm.daid_list),
            # 'dnid_list'             : cm.dnid_list,
            'dname_uuid_list'       : [convert_to_uuid(nid) for nid in cm.dnid_list],
            # FIXME: use qreq_ state not ibeis state
            'dname_list'            : ibs.get_name_texts(cm.dnid_list),
            'score_list'            : cm.score_list,
            'annot_score_list'      : cm.annot_score_list,
            'fm_list'               : cm.fm_list if hasattr(cm, 'fm_list') else None,
            'fsv_list'              : cm.fsv_list if hasattr(cm, 'fsv_list') else None,
            # Non-corresponding lists to above
            # 'unique_nids'         : cm.unique_nids,
            'unique_name_uuid_list' : [convert_to_uuid(nid) for nid in cm.unique_nids],
            # FIXME: use qreq_ state not ibeis state
            'unique_name_list'      : ibs.get_name_texts(cm.unique_nids),
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
    annot_inference = OrigAnnotInference(qreq_, cm_list, user_feedback)
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
def query_chips_graph_v2_matching_state_sync(ibs, matching_state_list):
    if len(matching_state_list) > 0:
        match_annot_uuid1_list = ut.take_column(matching_state_list, 0)
        match_annot_uuid2_list = ut.take_column(matching_state_list, 1)
        match_decision_list    = ut.take_column(matching_state_list, 2)
        match_tags_list        = ut.take_column(matching_state_list, 3)
        match_user_list        = ut.take_column(matching_state_list, 4)
        match_confidence_list  = ut.take_column(matching_state_list, 5)

        ibs.web_check_uuids([], match_annot_uuid1_list, [])
        ibs.web_check_uuids([], match_annot_uuid2_list, [])

        match_aid1_list = ibs.get_annot_aids_from_uuid(match_annot_uuid1_list)
        match_aid2_list = ibs.get_annot_aids_from_uuid(match_annot_uuid2_list)
        match_reviewed_list = [True] * len(match_aid1_list)

        # Add cleanly
        match_rowid_list = ibs.add_annotmatch(match_aid1_list, match_aid2_list,
                                              annotmatch_truth_list=match_decision_list,
                                              annotmatch_confidence_list=match_confidence_list,
                                              annotmatch_tag_text_list=match_tags_list,
                                              annotmatch_reviewed_list=match_reviewed_list,
                                              annotmatch_reviewer_list=match_user_list)
        # Set any values that already existed
        ibs.set_annotmatch_truth(match_rowid_list, match_decision_list)
        ibs.set_annotmatch_tag_text(match_rowid_list, match_tags_list)
        ibs.set_annotmatch_reviewer(match_rowid_list, match_user_list)
        ibs.set_annotmatch_reviewed(match_rowid_list, match_reviewed_list)
        ibs.set_annotmatch_confidence(match_rowid_list, match_confidence_list)


@register_ibs_method
@register_api('/api/query/graph/v2/', methods=['POST'])
def query_chips_graph_v2(ibs, annot_uuid_list=None,
                         annot_name_list=None,
                         matching_state_list=[],
                         query_config_dict={},
                         ready_callback_url=None,
                         ready_callback_method='POST',
                         finish_callback_url=None,
                         finish_callback_method='POST'):
    import ibeis

    valid_states = {
        'match': ['matched'],  # ['match', 'matched'],
        'nomatch': ['notmatched', 'nonmatch'],  # ['nomatch', 'notmatched', 'nonmatched', 'notmatch', 'non-match', 'not-match'],
        'notcomp' :  ['notcomparable'],
    }
    prefered_states = ut.take_column(valid_states.values(), 0)
    flat_states = ut.flatten(valid_states.values())

    def sanitize(state):
        state = state.strip().lower()
        state = ''.join(state.split())
        assert state in flat_states, 'matching_state_list has unrecognized states. Should be one of %r' % (prefered_states,)
        return state

    if annot_uuid_list is None:
        annot_uuid_list = ibs.get_annot_uuids(ibs.get_valid_aids())

    ibs.web_check_uuids([], annot_uuid_list, [])
    aid_list = ibs.get_annot_aids_from_uuid(annot_uuid_list)

    if annot_name_list is not None:
        assert len(annot_name_list) == len(annot_uuid_list)
        nid_list = ibs.add_names(annot_name_list)
        ibs.set_annot_name_rowids(aid_list, nid_list)

    ibs.query_chips_graph_v2_matching_state_sync(matching_state_list)

    query_annot_infr = ibeis.AnnotInference(ibs=ibs, aids=aid_list,
                                            autoinit=True)
    # Configure query_annot_infr
    query_annot_infr.init_web_mode()
    query_annot_infr.set_config(**query_config_dict)
    query_annot_infr.queue_params['pos_redun'] = 2
    query_annot_infr.queue_params['neg_redun'] = 2
    # Initialize
    query_annot_infr.reset_feedback('annotmatch', apply=True)
    query_annot_infr.ensure_mst()
    query_annot_infr.apply_nondynamic_update()
    # Register callbacks
    callback_dict = {
        'ready_callback_url'     : ready_callback_url,
        'ready_callback_method'  : ready_callback_method,
        'finish_callback_url'    : finish_callback_url,
        'finish_callback_method' : finish_callback_method,
    }
    query_annot_infr.set_callbacks(**callback_dict)
    query_annot_infr.main_loop()

    query_uuid = ut.random_uuid()
    assert query_uuid not in current_app.QUERY_V2_UUID_DICT
    current_app.QUERY_V2_UUID_DICT[query_uuid] = query_annot_infr
    return query_uuid


@register_ibs_method
def get_query_annot_infr_query_chips_graph_v2(ibs, query_uuid):
    query_annot_infr = current_app.QUERY_V2_UUID_DICT.get(query_uuid, None)
    # We could be redirecting to a newer query_annot_infr
    query_uuid_chain = [query_uuid]
    while isinstance(query_annot_infr, six.string_types):
        query_uuid_chain.append(query_annot_infr)
        query_annot_infr = current_app.QUERY_V2_UUID_DICT.get(query_annot_infr, None)
    if query_annot_infr is None:
        raise controller_inject.WebUnknownUUIDException(['query_uuid'], [query_uuid])
    return query_annot_infr, query_uuid_chain


@register_ibs_method
@register_api('/api/query/graph/v2/', methods=['GET'])
def sync_query_chips_graph_v2(ibs, query_uuid):
    query_annot_infr, _ = ibs.get_query_annot_infr_query_chips_graph_v2(query_uuid)

    # Ensure internal state is up to date
    query_annot_infr.relabel_using_reviews(rectify=True)
    edge_delta_df = query_annot_infr.match_state_delta(old='annotmatch', new='all')
    name_delta_df = query_annot_infr.get_ibeis_name_delta()
    query_annot_infr.write_ibeis_staging_feedback()
    query_annot_infr.write_ibeis_annotmatch_feedback(edge_delta_df)
    query_annot_infr.write_ibeis_name_assignment(name_delta_df)

    edge_delta_df_ = edge_delta_df.reset_index()

    # Set residual matching data
    aid1_list = edge_delta_df_['aid1']
    aid2_list = edge_delta_df_['aid2']
    annot_uuid1_list = ibs.get_annot_uuids(aid1_list)
    annot_uuid2_list = ibs.get_annot_uuids(aid2_list)
    decision_list = ut.take(ibs.const.REVIEW.CODE_TO_INT, edge_delta_df_['new_decision'])
    tags_list = [';'.join(tags) for tags in edge_delta_df_['new_tags']]
    reviewer_list = edge_delta_df_['new_user_id']
    conf_list = ut.dict_take(ibs.const.CONFIDENCE.CODE_TO_INT, edge_delta_df_['new_confidence'], None)

    matching_state_list = zip(
        annot_uuid1_list,
        annot_uuid2_list,
        decision_list,
        tags_list,
        reviewer_list,
        conf_list,
    )
    ret_dict = {
        'matching_state_list': matching_state_list,
        'name_list': name_delta_df,
    }
    return ret_dict


@register_ibs_method
@register_api('/api/query/graph/v2/', methods=['PUT'])
def add_annots_query_chips_graph_v2(ibs, query_uuid, annot_uuid_list,
                                    matching_state_list=[]):
    query_annot_infr, _ = ibs.get_query_annot_infr_query_chips_graph_v2(query_uuid)
    ibs.web_check_uuids([], annot_uuid_list, [])
    ibs.query_chips_graph_v2_matching_state_sync(matching_state_list)
    aid_list = ibs.get_annot_aids_from_uuid(annot_uuid_list)
    query_uuid_ = query_annot_infr.add_annots(aid_list)
    current_app.QUERY_V2_UUID_DICT[query_uuid_] = query_annot_infr
    current_app.QUERY_V2_UUID_DICT[query_uuid] = query_uuid_
    return query_uuid_


@register_ibs_method
@register_api('/api/query/graph/v2/', methods=['DELETE'])
def delete_query_chips_graph_v2(ibs, query_uuid):
    values = ibs.get_query_annot_infr_query_chips_graph_v2(query_uuid)
    query_annot_infr, query_uuid_chain = values
    sync_response = ibs.sync_query_chips_graph_v2(query_uuid)
    del query_annot_infr
    for query_uuid_ in query_uuid_chain:
        if query_uuid_ in current_app.QUERY_V2_UUID_DICT:
            current_app.QUERY_V2_UUID_DICT[query_uuid_] = None
            current_app.QUERY_V2_UUID_DICT.pop(query_uuid_)
    return sync_response


@register_ibs_method
@register_api('/api/query/chip/', methods=['GET'])
def query_chips(ibs, qaid_list=None, daid_list=None, cfgdict=None,
                use_cache=None, use_bigcache=None, qreq_=None,
                return_request=False, verbose=pipeline.VERB_PIPELINE,
                save_qcache=None, prog_hook=None, return_cm_dict=False,
                return_cm_simple_dict=False):
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
        URL:    /api/query/chip/

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
        >>> ibs = ibeis.opendb_test(db='testdb1')
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
        >>> ibs = ibeis.opendb_test(db='testdb1')
        >>> cfgdict = {'pipeline_root':'BC_DTW'}
        >>> qreq_ = ibs.new_query_request(qaid_list, daid_list, cfgdict=cfgdict, verbose=True)
        >>> cm = ibs.query_chips(qreq_=qreq_)[0]
        >>> ut.quit_if_noshow()
        >>> cm.ishow_analysis(qreq_)
        >>> ut.show_if_requested()
    """
    # The qaid and daid objects are allowed to be None if qreq_ is
    # specified
    if qreq_ is None:
        assert qaid_list is not None, 'do not specify qaids and qreq'
        assert daid_list is not None, 'do not specify daids and qreq'
        qaid_list, was_scalar = ut.wrap_iterable(qaid_list)
        if daid_list is None:
            daid_list = ibs.get_valid_aids()
        qreq_ = ibs.new_query_request(qaid_list, daid_list,
                                      cfgdict=cfgdict, verbose=verbose)
    else:
        assert qaid_list is None, 'do not specify qreq and qaids'
        assert daid_list is None, 'do not specify qreq and daids'
        was_scalar = False
    cm_list = qreq_.execute()
    assert isinstance(cm_list, list), (
        'Chip matches were not returned as a list')

    # Convert to cm_list
    if return_cm_simple_dict:
        for cm in cm_list:
            cm.qauuid = ibs.get_annot_uuids(cm.qaid)
            cm.dauuid_list = ibs.get_annot_uuids(cm.daid_list)
        keys = ['qaid', 'daid_list', 'score_list', 'qauuid', 'dauuid_list']
        cm_list = [ut.dict_subset(cm.to_dict(), keys) for cm in cm_list]
    elif return_cm_dict:
        cm_list = [cm.to_dict() for cm in cm_list]

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
