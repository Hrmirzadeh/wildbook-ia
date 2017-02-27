# -*- coding: utf-8 -*-
"""
IBEIS CORE
Defines the core dependency cache supported by the image analysis api

Extracts detection results from images and applies additional processing
automatically


Ex
    python -m ibeis.control.IBEISControl --test-show_depc_image_graph --show
    python -m ibeis.control.IBEISControl --test-show_depc_image_graph --show --reduced


TODO:

NOTES:
    HOW TO DESIGN INTERACTIVE PLOTS:
        decorate as interactive

        depc.get_property(recompute=True)

        instead of calling preproc as a generator and then adding,
        calls preproc and passes in a callback function.
        preproc spawns interaction and must call callback function when finished.

        callback function adds the rowids to the table.

Needed Tables:
    Detections
    QualityClassifier
    ViewpointClassifier

"""
from __future__ import absolute_import, division, print_function, unicode_literals
from six.moves import zip
import dtool
import utool as ut
import numpy as np
import vtool as vt
import cv2
from ibeis.control.controller_inject import register_preprocs
(print, rrr, profile) = ut.inject2(__name__, '[core_images]')


register_preproc = register_preprocs['image']


class ThumbnailConfig(dtool.Config):
    _param_info_list = [
        ut.ParamInfo('draw_annots', True, hideif=True),
        ut.ParamInfo('thumbsize', None, type_=None, hideif=None),
        ut.ParamInfo('ext', '.png', hideif='.png'),
        ut.ParamInfo('force_serial', False, hideif=False),
    ]


@register_preproc(
    tablename='thumbnails', parents=['images'],
    colnames=['img', 'width', 'height'],
    coltypes=[('extern', vt.imread, vt.imwrite), int, int],
    configclass=ThumbnailConfig,
    fname='thumbcache',
    rm_extern_on_delete=True,
    chunksize=256,
)
def compute_thumbnails(depc, gid_list, config=None):
    r"""
    Computers the thumbnail for a given input image

    Args:
        depc (ibeis.depends_cache.DependencyCache):
        gid_list (list):  list of image rowids
        config (dict): (default = None)

    Yields:
        (uri, int, int): tup

    CommandLine:
        ibeis --tf compute_thumbnails --show --db PZ_MTEST

    Example:
        >>> # ENABLE_DOCTEST
        >>> from ibeis.core_images import *  # NOQA
        >>> import ibeis
        >>> defaultdb = 'testdb1'
        >>> ibs = ibeis.opendb(defaultdb=defaultdb)
        >>> depc = ibs.depc_image
        >>> gid_list = ibs.get_valid_gids()[0:10]
        >>> thumbs = depc.get_property('thumbnails', gid_list, 'img', config={'thumbsize': 221})
        >>> ut.quit_if_noshow()
        >>> import plottool as pt
        >>> iteract_obj = pt.interact_multi_image.MultiImageInteraction(thumbs, nPerPage=4)
        >>> iteract_obj.start()
        >>> pt.show_if_requested()
    """

    ibs = depc.controller
    draw_annots = config['draw_annots']
    thumbsize = config['thumbsize']
    if thumbsize is None:
        cfg = ibs.cfg.other_cfg
        thumbsize = cfg.thumb_size if draw_annots else cfg.thumb_bare_size
    thumbsize_list = [thumbsize] * len(gid_list)
    gpath_list = ibs.get_image_paths(gid_list)
    orient_list = ibs.get_image_orientation(gid_list)
    aids_list = ibs.get_image_aids(gid_list)
    if draw_annots:
        bboxes_list = ibs.unflat_map(ibs.get_annot_bboxes, aids_list)
        thetas_list = ibs.unflat_map(ibs.get_annot_thetas, aids_list)
    else:
        bboxes_list = [ [] for aids in aids_list ]
        thetas_list = [ [] for aids in aids_list ]

    # Execute all tasks in parallel
    args_list = list(zip(thumbsize_list, gpath_list, orient_list, bboxes_list,
                         thetas_list))
    genkw = {
        'ordered': False,
        'chunksize': 256,
        'freq': 50,
        #'adjust': True,
        'force_serial': ibs.force_serial or config['force_serial'],
    }
    gen = ut.generate(draw_thumb_helper, args_list, nTasks=len(args_list), **genkw)
    for val in gen:
        yield val


def draw_thumb_helper(tup):
    thumbsize, gpath, orient, bbox_list, theta_list = tup
    # time consuming
    # img = vt.imread(gpath, orient=orient)
    img = vt.imread(gpath)
    (gh, gw) = img.shape[0:2]
    img_size = (gw, gh)
    if isinstance(thumbsize, int):
        max_dsize = (thumbsize, thumbsize)
        dsize, sx, sy = vt.resized_clamped_thumb_dims(img_size, max_dsize)
    elif isinstance(thumbsize, tuple) and len(thumbsize) == 2:
        th, tw = thumbsize
        dsize, sx, sy = thumbsize, tw / gw, th / gh
    else:
        raise ValueError('Incompatible thumbsize')
    new_verts_list = list(vt.scaled_verts_from_bbox_gen(bbox_list, theta_list, sx, sy))
    # -----------------
    # Actual computation
    thumb = vt.resize(img, dsize)
    orange_bgr = (0, 128, 255)
    for new_verts in new_verts_list:
        thumb = vt.draw_verts(thumb, new_verts, color=orange_bgr, thickness=2)
    width, height = dsize
    return thumb, width, height


class ClassifierConfig(dtool.Config):
    _param_info_list = [
        ut.ParamInfo('classifier_algo', 'cnn', valid_values=['cnn', 'svm']),
        ut.ParamInfo('classifier_weight_filepath', None),
    ]
    _sub_config_list = [
        ThumbnailConfig
    ]


@register_preproc(
    tablename='classifier', parents=['images'],
    colnames=['score', 'class'],
    coltypes=[float, str],
    configclass=ClassifierConfig,
    fname='detectcache',
    chunksize=1024,
)
def compute_classifications(depc, gid_list, config=None):
    r"""
    Extracts the detections for a given input image

    Args:
        depc (ibeis.depends_cache.DependencyCache):
        gid_list (list):  list of image rowids
        config (dict): (default = None)

    Yields:
        (float, str): tup

    CommandLine:
        ibeis compute_classifications

    Example:
        >>> # DISABLE_DOCTEST
        >>> from ibeis.core_images import *  # NOQA
        >>> import ibeis
        >>> defaultdb = 'PZ_MTEST'
        >>> ibs = ibeis.opendb(defaultdb=defaultdb)
        >>> depc = ibs.depc_image
        >>> gid_list = ibs.get_valid_gids()[0:8]
        >>> # depc.delete_property('classifier', gid_list)
        >>> results = depc.get_property('classifier', gid_list, None)
        >>> print(results)
        >>> depc = ibs.depc_image
        >>> config = {'classifier_algo': 'svm'}
        >>> depc.delete_property('classifier', gid_list, config=config)
        >>> results = depc.get_property('classifier', gid_list, None, config=config)
        >>> print(results)
        >>> config = {'classifier_algo': 'svm', 'classifier_weight_filepath': 'localizer-zebra-10'}
        >>> depc.delete_property('classifier', gid_list, config=config)
        >>> results = depc.get_property('classifier', gid_list, None, config=config)
        >>> print(results)
    """
    print('[ibs] Process Image Classifications')
    print('config = %r' % (config,))
    # Get controller
    ibs = depc.controller
    depc = ibs.depc_image
    if config['classifier_algo'] in ['cnn']:
        config_ = {
            'draw_annots' : False,
            'thumbsize'   : (192, 192),
        }
        thumbnail_list = depc.get_property('thumbnails', gid_list, 'img', config=config_)
        result_list = ibs.generate_thumbnail_class_list(thumbnail_list, **config_)
    elif config['classifier_algo'] in ['svm']:
        from ibeis.algo.detect.svm import classify
        config_ = {
            'algo': 'resnet'
        }
        vector_list = depc.get_property('features', gid_list, 'vector', config=config_)
        classifier_weight_filepath = config['classifier_weight_filepath']
        result_list = classify(vector_list, weight_filepath=classifier_weight_filepath)
    else:
        raise ValueError('specified classifier algo is not supported in config = %r' % (config, ))

    # yield detections
    for result in result_list:
        yield result


class FeatureConfig(dtool.Config):
    _param_info_list = [
        ut.ParamInfo('algo', 'vgg16', valid_values=['vgg', 'vgg16', 'vgg19', 'resnet', 'inception']),
        ut.ParamInfo('flatten', True),
    ]
    _sub_config_list = [
        ThumbnailConfig
    ]


@register_preproc(
    tablename='features', parents=['images'],
    colnames=['vector'],
    coltypes=[np.ndarray],
    configclass=FeatureConfig,
    fname='featcache',
    chunksize=256,
)
def compute_features(depc, gid_list, config=None):
    r"""
    Computes features on images using pre-trained state-of-the-art models in
    Keras

    Args:
        depc (ibeis.depends_cache.DependencyCache):
        gid_list (list):  list of image rowids
        config (dict): (default = None)

    Yields:
        (np.ndarray, ): tup

    CommandLine:
        ibeis compute_features

    CommandLine:
        python -m ibeis.core_images compute_features --show

    Example:
        >>> # DISABLE_DOCTEST
        >>> from ibeis.core_images import *  # NOQA
        >>> import ibeis
        >>> defaultdb = 'PZ_MTEST'
        >>> ibs = ibeis.opendb(defaultdb=defaultdb)
        >>> depc = ibs.depc_image
        >>> print(depc.get_tablenames())
        >>> gid_list = ibs.get_valid_gids()[:16]
        >>> config = {'algo': 'vgg16'}
        >>> depc.delete_property('features', gid_list, config=config)
        >>> features = depc.get_property('features', gid_list, 'vector', config=config)
        >>> print(features)
        >>> config = {'algo': 'vgg19'}
        >>> depc.delete_property('features', gid_list, config=config)
        >>> features = depc.get_property('features', gid_list, 'vector', config=config)
        >>> print(features)
        >>> config = {'algo': 'resnet'}
        >>> depc.delete_property('features', gid_list, config=config)
        >>> features = depc.get_property('features', gid_list, 'vector', config=config)
        >>> print(features)
        >>> config = {'algo': 'inception'}
        >>> depc.delete_property('features', gid_list, config=config)
        >>> features = depc.get_property('features', gid_list, 'vector', config=config)
        >>> print(features)
    """
    from keras.preprocessing import image as preprocess_image
    print('[ibs] Preprocess Features')
    print('config = %r' % (config,))
    # Get controller
    ibs = depc.controller
    ibs.assert_valid_gids(gid_list)
    thumbnail_config = {
        'draw_annots' : False,
        'thumbsize'   : (500, 500),
    }
    thumbpath_list = depc.get('thumbnails', gid_list, 'img', config=thumbnail_config,
                              read_extern=False, ensure=True)

    target_size = (224, 224)
    ######################################################################################
    if config['algo'] in ['vgg', 'vgg16']:
        from keras.applications.vgg16 import VGG16 as MODEL_CLASS
        from keras.applications.vgg16 import preprocess_input
    ######################################################################################
    elif config['algo'] in ['vgg19']:
        from keras.applications.vgg19 import VGG19 as MODEL_CLASS
        from keras.applications.vgg19 import preprocess_input
    ######################################################################################
    elif config['algo'] in ['resnet']:
        from keras.applications.resnet50 import ResNet50 as MODEL_CLASS  # NOQA
        from keras.applications.resnet50 import preprocess_input
    ######################################################################################
    elif config['algo'] in ['inception']:
        from keras.applications.inception_v3 import InceptionV3 as MODEL_CLASS  # NOQA
        from keras.applications.inception_v3 import preprocess_input
        target_size = (299, 299)
    ######################################################################################
    else:
        raise ValueError('specified feature algo is not supported in config = %r' % (config, ))

    # Build model
    model = MODEL_CLASS(include_top=False)

    thumbpath_iter = ut.ProgIter(thumbpath_list, lbl='forward inference', bs=True)
    for thumbpath in thumbpath_iter:
        image = preprocess_image.load_img(thumbpath, target_size=target_size)
        image_array = preprocess_image.img_to_array(image)
        image_array = np.expand_dims(image_array, axis=0)
        image_array = preprocess_input(image_array)
        features = model.predict(image_array)
        if config['flatten']:
            features = features.flatten()
        yield (features, )


class LocalizerConfig(dtool.Config):
    _param_info_list = [
        ut.ParamInfo('algo', 'yolo', valid_values=['yolo', 'ssd', 'darknet', 'rf', 'fast-rcnn', 'faster-rcnn', 'selective-search', 'selective-search-rcnn', '_COMBINED']),
        ut.ParamInfo('sensitivity', 0.0),
        ut.ParamInfo('species', 'zebra_plains'),
        ut.ParamInfo('config_filepath', None),
        ut.ParamInfo('weight_filepath', None),
        ut.ParamInfo('class_filepath', None),
        ut.ParamInfo('grid', False),
    ]
    _sub_config_list = [
        ThumbnailConfig
    ]


@register_preproc(
    tablename='localizations', parents=['images'],
    colnames=['score', 'bboxes', 'thetas', 'confs', 'classes'],
    coltypes=[float, np.ndarray, np.ndarray, np.ndarray, np.ndarray],
    configclass=LocalizerConfig,
    fname='detectcache',
    chunksize=256,
)
def compute_localizations(depc, gid_list, config=None):
    r"""
    Extracts the localizations for a given input image

    Args:
        depc (ibeis.depends_cache.DependencyCache):
        gid_list (list):  list of image rowids
        config (dict): (default = None)

    Yields:
        (float, np.ndarray, np.ndarray, np.ndarray, np.ndarray): tup

    CommandLine:
        ibeis compute_localizations

    CommandLine:
        python -m ibeis.core_images compute_localizations --show

    Example:
        >>> # DISABLE_DOCTEST
        >>> from ibeis.core_images import *  # NOQA
        >>> import ibeis
        >>> defaultdb = 'PZ_MTEST'
        >>> ibs = ibeis.opendb(defaultdb=defaultdb)
        >>> depc = ibs.depc_image
        >>> print(depc.get_tablenames())
        >>> gid_list = ibs.get_valid_gids()[:16]
        >>> config = {'algo': 'darknet', 'config_filepath': 'pretrained-v2-pascal'}
        >>> depc.delete_property('localizations', gid_list, config=config)
        >>> detects = depc.get_property('localizations', gid_list, 'bboxes', config=config)
        >>> print(detects)
        >>> config = {'algo': 'darknet', 'config_filepath': 'pretrained-v2-large-pascal'}
        >>> depc.delete_property('localizations', gid_list, config=config)
        >>> detects = depc.get_property('localizations', gid_list, 'bboxes', config=config)
        >>> print(detects)
        >>> config = {'algo': 'darknet', 'config_filepath': 'pretrained-tiny-pascal'}
        >>> depc.delete_property('localizations', gid_list, config=config)
        >>> detects = depc.get_property('localizations', gid_list, 'bboxes', config=config)
        >>> print(detects)
        >>> config = {'algo': 'darknet', 'config_filepath': 'pretrained-v2-large-coco'}
        >>> depc.delete_property('localizations', gid_list, config=config)
        >>> detects = depc.get_property('localizations', gid_list, 'bboxes', config=config)
        >>> print(detects)
        >>> config = {'algo': 'darknet', 'config_filepath': 'pretrained-tiny-coco'}
        >>> depc.delete_property('localizations', gid_list, config=config)
        >>> detects = depc.get_property('localizations', gid_list, 'bboxes', config=config)
        >>> print(detects)
        >>> config = {'algo': 'yolo'}
        >>> depc.delete_property('localizations', gid_list, config=config)
        >>> detects = depc.get_property('localizations', gid_list, 'bboxes', config=config)
        >>> print(detects)
        >>> config = {'algo': 'rf'}
        >>> depc.delete_property('localizations', gid_list, config=config)
        >>> detects = depc.get_property('localizations', gid_list, 'bboxes', config=config)
        >>> print(detects)
        >>> config = {'algo': 'selective-search'}
        >>> depc.delete_property('localizations', gid_list, config=config)
        >>> detects = depc.get_property('localizations', gid_list, 'bboxes', config=config)
        >>> print(detects)
        >>> config = {'algo': 'selective-search-rcnn'}
        >>> depc.delete_property('localizations', gid_list, config=config)
        >>> detects = depc.get_property('localizations', gid_list, 'bboxes', config=config)
        >>> print(detects)
        >>> config = {'algo': 'faster-rcnn', 'config_filepath': 'pretrained-vgg-pascal'}
        >>> depc.delete_property('localizations', gid_list, config=config)
        >>> detects = depc.get_property('localizations', gid_list, 'bboxes', config=config)
        >>> print(detects)
        >>> config = {'algo': 'faster-rcnn', 'config_filepath': 'pretrained-zf-pascal'}
        >>> depc.delete_property('localizations', gid_list, config=config)
        >>> detects = depc.get_property('localizations', gid_list, 'bboxes', config=config)
        >>> print(detects)
        >>> config = {'algo': 'faster-rcnn', 'config_filepath': 'pretrained-vgg-ilsvrc'}
        >>> depc.delete_property('localizations', gid_list, config=config)
        >>> detects = depc.get_property('localizations', gid_list, 'bboxes', config=config)
        >>> print(detects)
        >>> config = {'algo': 'faster-rcnn', 'config_filepath': 'pretrained-zf-ilsvrc'}
        >>> depc.delete_property('localizations', gid_list, config=config)
        >>> detects = depc.get_property('localizations', gid_list, 'bboxes', config=config)
        >>> print(detects)
        >>> config = {'algo': 'ssd', 'config_filepath': 'pretrained-300-pascal'}
        >>> depc.delete_property('localizations', gid_list, config=config)
        >>> detects = depc.get_property('localizations', gid_list, 'bboxes', config=config)
        >>> print(detects)
        >>> config = {'algo': 'ssd', 'config_filepath': 'pretrained-512-pascal'}
        >>> depc.delete_property('localizations', gid_list, config=config)
        >>> detects = depc.get_property('localizations', gid_list, 'bboxes', config=config)
        >>> print(detects)
        >>> config = {'algo': 'ssd', 'config_filepath': 'pretrained-300-pascal-plus'}
        >>> depc.delete_property('localizations', gid_list, config=config)
        >>> detects = depc.get_property('localizations', gid_list, 'bboxes', config=config)
        >>> print(detects)
        >>> config = {'algo': 'ssd', 'config_filepath': 'pretrained-512-pascal-plus'}
        >>> depc.delete_property('localizations', gid_list, config=config)
        >>> detects = depc.get_property('localizations', gid_list, 'bboxes', config=config)
        >>> print(detects)
        >>> config = {'algo': 'ssd', 'config_filepath': 'pretrained-300-coco'}
        >>> depc.delete_property('localizations', gid_list, config=config)
        >>> detects = depc.get_property('localizations', gid_list, 'bboxes', config=config)
        >>> print(detects)
        >>> config = {'algo': 'ssd', 'config_filepath': 'pretrained-512-coco'}
        >>> depc.delete_property('localizations', gid_list, config=config)
        >>> detects = depc.get_property('localizations', gid_list, 'bboxes', config=config)
        >>> print(detects)
        >>> config = {'algo': 'ssd', 'config_filepath': 'pretrained-300-ilsvrc'}
        >>> depc.delete_property('localizations', gid_list, config=config)
        >>> detects = depc.get_property('localizations', gid_list, 'bboxes', config=config)
        >>> print(detects)
        >>> config = {'algo': 'ssd', 'config_filepath': 'pretrained-500-ilsvrc'}
        >>> depc.delete_property('localizations', gid_list, config=config)
        >>> detects = depc.get_property('localizations', gid_list, 'bboxes', config=config)
        >>> print(detects)
        >>> config = {'algo': '_COMBINED'}
        >>> depc.delete_property('localizations', gid_list, config=config)
        >>> detects = depc.get_property('localizations', gid_list, 'bboxes', config=config)
        >>> print(detects)
    """
    def package_to_numpy(key_list, result_list, score):
        temp = [
            [
                key[0] if isinstance(key, tuple) else result[key]
                for key in key_list
            ]
            for result in result_list
        ]
        return (
            score,
            np.array([ _[0:4] for _ in temp ]),
            np.array([ _[4]   for _ in temp ]),
            np.array([ _[5]   for _ in temp ]),
            np.array([ _[6]   for _ in temp ]),
        )

    COMBINED = False
    print('[ibs] Preprocess Localizations')
    print('config = %r' % (config,))
    # Get controller
    ibs = depc.controller
    ibs.assert_valid_gids(gid_list)
    base_key_list = ['xtl', 'ytl', 'width', 'height', 'theta', 'confidence', 'class']
    # Temporary for all detectors
    base_key_list[4] = (0.0, )  # Theta

    ######################################################################################
    if config['algo'] in ['pydarknet', 'yolo', 'cnn']:
        from ibeis.algo.detect import yolo
        print('[ibs] detecting using PyDarknet CNN YOLO')
        detect_gen = yolo.detect_gid_list(ibs, gid_list, **config)
    ######################################################################################
    elif config['algo'] in ['rf']:
        from ibeis.algo.detect import randomforest
        print('[ibs] detecting using Random Forests')
        base_key_list[6] = (config['species'], )  # class == species
        detect_gen = randomforest.detect_gid_list_with_species(ibs, gid_list, **config)
    ######################################################################################
    elif config['algo'] in ['selective-search']:
        from ibeis.algo.detect import selectivesearch
        print('[ibs] detecting using Selective Search')
        matlab_command = 'selective_search'
        detect_gen = selectivesearch.detect_gid_list(ibs, gid_list, matlab_command=matlab_command, **config)
    ######################################################################################
    elif config['algo'] in ['selective-search-rcnn']:
        from ibeis.algo.detect import selectivesearch
        print('[ibs] detecting using Selective Search (R-CNN)')
        matlab_command = 'selective_search_rcnn'
        detect_gen = selectivesearch.detect_gid_list(ibs, gid_list, matlab_command=matlab_command, **config)
    ######################################################################################
    # elif config['algo'] in ['fast-rcnn']:
    #     from ibeis.algo.detect import fasterrcnn
    #     print('[ibs] detecting using CNN Fast R-CNN')
    #     detect_gen = fasterrcnn.detect_gid_list(ibs, gid_list, **config)
    ######################################################################################
    elif config['algo'] in ['faster-rcnn']:
        from ibeis.algo.detect import fasterrcnn
        print('[ibs] detecting using CNN Faster R-CNN')
        detect_gen = fasterrcnn.detect_gid_list(ibs, gid_list, **config)
    ######################################################################################
    elif config['algo'] in ['darknet']:
        from ibeis.algo.detect import darknet
        print('[ibs] detecting using Darknet CNN YOLO')
        detect_gen = darknet.detect_gid_list(ibs, gid_list, **config)
    ######################################################################################
    elif config['algo'] in ['ssd']:
        from ibeis.algo.detect import ssd
        print('[ibs] detecting using CNN SSD')
        detect_gen = ssd.detect_gid_list(ibs, gid_list, **config)
    ######################################################################################
    elif config['algo'] in ['_COMBINED']:
        COMBINED = True

        def _get_localizations(depc, gid_list, algo, config_filepath=None):
            config = {'algo': algo, 'config_filepath': config_filepath}
            return [
                depc.get_property('localizations', gid_list, 'score',   config=config),
                depc.get_property('localizations', gid_list, 'bboxes',  config=config),
                depc.get_property('localizations', gid_list, 'thetas',  config=config),
                depc.get_property('localizations', gid_list, 'confs',   config=config),
                depc.get_property('localizations', gid_list, 'classes', config=config),
            ]

        metadata = {}

        metadata['SS1']     = _get_localizations(depc, gid_list, 'selective-search')

        # Get Localizations
        metadata['YOLO1']  = _get_localizations(depc, gid_list, 'darknet', 'pretrained-tiny-pascal')
        metadata['YOLO2']  = _get_localizations(depc, gid_list, 'darknet', 'pretrained-v2-pascal')
        # metadata['YOLO3']  = _get_localizations(depc, gid_list, 'darknet', 'pretrained-v2-large-pascal')

        metadata['FRCNN1'] = _get_localizations(depc, gid_list, 'faster-rcnn', 'pretrained-zf-pascal')
        metadata['FRCNN2'] = _get_localizations(depc, gid_list, 'faster-rcnn', 'pretrained-vgg-pascal')

        metadata['SSD1']   = _get_localizations(depc, gid_list, 'ssd', 'pretrained-300-pascal')
        metadata['SSD2']   = _get_localizations(depc, gid_list, 'ssd', 'pretrained-512-pascal')
        metadata['SSD3']   = _get_localizations(depc, gid_list, 'ssd', 'pretrained-300-pascal-plus')
        metadata['SSD4']   = _get_localizations(depc, gid_list, 'ssd', 'pretrained-512-pascal-plus')

        detect_gen = None
        # Get Combined
        metadata['_COMBINED'] = []
        for key in sorted(metadata.keys()):
            if key == 'COMBINED':
                continue
            if len(metadata['_COMBINED']) == 0:
                # Initializing combined list, simply append
                metadata['_COMBINED'] = list(metadata[key])
            else:
                # Combined already initialized, hstack new metadata
                current = metadata['_COMBINED']
                detect = metadata[key]
                for index in range(len(current)):
                    # print(index, current[index].shape, detect[index].shape)
                    new = []
                    for image in range(len(detect[index])):
                        # print(current[index][image].shape, detect[index][image].shape)
                        if index == 0:
                            temp = 0.0
                        elif len(current[index][image].shape) == 1:
                            temp = np.hstack((current[index][image], detect[index][image]))
                        else:
                            temp = np.vstack((current[index][image], detect[index][image]))
                        new.append(temp)
                    metadata['_COMBINED'][index] = np.array(new)

        results_list = list(zip(*metadata['_COMBINED']))
        for results in results_list:
            yield results
    # ######################################################################################
    else:
        raise ValueError('specified detection algo is not supported in config = %r' % (config, ))

    if not COMBINED:
        # yield detections
        for gid, gpath, result_list in detect_gen:
            score = 0.0
            yield package_to_numpy(base_key_list, result_list, score)


def get_localization_chips_worker(tup):
    gid, img, bbox_list, theta_list, target_size = tup
    target_size_list = [target_size] * len(bbox_list)

    # Build transformation from image to chip
    M_list = [
        vt.get_image_to_chip_transform(bbox, new_size, theta)
        for bbox, theta, new_size in zip(bbox_list, theta_list, target_size_list)
    ]

    # Extract "chips"
    flags = cv2.INTER_LANCZOS4
    borderMode = cv2.BORDER_CONSTANT
    warpkw = dict(flags=flags, borderMode=borderMode)

    def _compute_localiation_chip(tup):
        new_size, M = tup
        chip = cv2.warpAffine(img, M[0:2], tuple(new_size), **warpkw)
        # cv2.imshow('', chip)
        # cv2.waitKey()
        msg = 'Chip shape %r does not agree with target size %r' % (chip.shape, target_size, )
        assert chip.shape[0] == new_size[0] and chip.shape[1] == new_size[1], msg
        return chip

    arg_list = list(zip(target_size_list, M_list))
    chip_list = [_compute_localiation_chip(tup_) for tup_ in arg_list]
    gid_list = [gid] * len(chip_list)
    return gid_list, chip_list


def get_localization_masks_worker(tup):
    gid, img, bbox_list, theta_list, target_size = tup
    target_size_list = [target_size] * len(bbox_list)
    verts_list = vt.geometry.scaled_verts_from_bbox_gen(bbox_list, theta_list)

    # Extract "masks"
    interpolation = cv2.INTER_LANCZOS4
    warpkw = dict(interpolation=interpolation)
    fill_pixel_value = (128, 128, 128)  # Grey-scale medium

    def _compute_localiation_mask(tup):
        new_size, vert_list = tup
        # Copy the image, mask out the patch
        img_ = np.copy(img)
        vert_list_ = np.array(vert_list, dtype=np.int32)
        cv2.fillConvexPoly(img_, vert_list_, fill_pixel_value)
        # Resize the image
        mask = cv2.resize(img_, tuple(new_size), **warpkw)
        # cv2.imshow('', mask)
        # cv2.waitKey()
        msg = 'Chip shape %r does not agree with target size %r' % (mask.shape, new_size, )
        assert mask.shape[0] == new_size[0] and mask.shape[1] == new_size[1], msg
        return mask

    arg_list = list(zip(target_size_list, verts_list))
    mask_list = [_compute_localiation_mask(tup_) for tup_ in arg_list]
    gid_list = [gid] * len(mask_list)
    return gid_list, mask_list


def get_localization_chips(ibs, loc_id_list, target_size=(128, 128)):
    depc = ibs.depc_image
    gid_list_ = depc.get_ancestor_rowids('localizations', loc_id_list, 'images')
    assert len(gid_list_) == len(loc_id_list)

    # Grab the localizations
    bboxes_list = depc.get_native('localizations', loc_id_list, 'bboxes')
    len_list = [len(bbox_list) for bbox_list in bboxes_list]
    avg = sum(len_list) / len(len_list)
    args = (len(loc_id_list), min(len_list), avg, max(len_list), sum(len_list), )
    print('Extracting %d localization chips (min: %d, avg: %0.02f, max: %d, total: %d)' % args)
    thetas_list = depc.get_native('localizations', loc_id_list, 'thetas')

    OLD = True
    if OLD:
        gids_list = [
            np.array([gid] * len(bbox_list))
            for gid, bbox_list in zip(gid_list_, bboxes_list)
        ]
        # Flatten all of these lists for efficiency
        bbox_list      = ut.flatten(bboxes_list)
        theta_list     = ut.flatten(thetas_list)
        gid_list       = ut.flatten(gids_list)
        bbox_size_list = ut.take_column(bbox_list, [2, 3])
        newsize_list   = [target_size] * len(bbox_list)

        # Checks
        invalid_flags = [w == 0 or h == 0 for (w, h) in bbox_size_list]
        invalid_bboxes = ut.compress(bbox_list, invalid_flags)
        assert len(invalid_bboxes) == 0, 'invalid bboxes=%r' % (invalid_bboxes,)

        # Build transformation from image to chip
        M_list = [
            vt.get_image_to_chip_transform(bbox, new_size, theta)
            for bbox, theta, new_size in zip(bbox_list, theta_list, newsize_list)
        ]

        # Extract "chips"
        flags = cv2.INTER_LANCZOS4
        borderMode = cv2.BORDER_CONSTANT
        warpkw = dict(flags=flags, borderMode=borderMode)

        last_gid = None
        chip_list = []
        arg_list = list(zip(gid_list, newsize_list, M_list))
        for tup in ut.ProgIter(arg_list, lbl='computing localization chips', bs=True):
            gid, new_size, M = tup
            if gid != last_gid:
                img = ibs.get_image_imgdata(gid)
                last_gid = gid
            chip = cv2.warpAffine(img, M[0:2], tuple(new_size), **warpkw)
            # cv2.imshow('', chip)
            # cv2.waitKey()
            msg = 'Chip shape %r does not agree with target size %r' % (chip.shape, target_size, )
            assert chip.shape[0] == target_size[0] and chip.shape[1] == target_size[1], msg
            chip_list.append(chip)
    else:
        target_size_list = [target_size] * len(bboxes_list)
        img_list = [ibs.get_image_imgdata(gid) for gid in gid_list_]
        arg_iter = list(zip(gid_list_, img_list, bboxes_list, thetas_list,
                            target_size_list))
        result_list = ut.util_parallel.generate(get_localization_chips_worker, arg_iter,
                                                ordered=True)
        # Compute results
        result_list = list(result_list)
        # Extract results
        gids_list = ut.take_column(result_list, 0)
        chips_list = ut.take_column(result_list, 1)
        # Explicitly garbage collect large list of chips
        result_list = None
        # Flatten results
        gid_list = ut.flatten(gids_list)
        chip_list = ut.flatten(chips_list)
        assert len(gid_list) == len(chip_list)

    return gid_list_, gid_list, chip_list


def get_localization_masks(ibs, loc_id_list, target_size=(128, 128)):
    depc = ibs.depc_image
    gid_list_ = depc.get_ancestor_rowids('localizations', loc_id_list, 'images')
    assert len(gid_list_) == len(loc_id_list)

    # Grab the localizations
    bboxes_list = depc.get_native('localizations', loc_id_list, 'bboxes')
    len_list = [len(bbox_list) for bbox_list in bboxes_list]
    avg = sum(len_list) / len(len_list)
    args = (len(loc_id_list), min(len_list), avg, max(len_list), sum(len_list), )
    print('Extracting %d localization masks (min: %d, avg: %0.02f, max: %d, total: %d)' % args)
    thetas_list = depc.get_native('localizations', loc_id_list, 'thetas')

    OLD = True
    if OLD:
        gids_list = [
            np.array([gid] * len(bbox_list))
            for gid, bbox_list in zip(gid_list_, bboxes_list)
        ]
        # Flatten all of these lists for efficiency
        bbox_list      = ut.flatten(bboxes_list)
        theta_list     = ut.flatten(thetas_list)
        verts_list     = vt.geometry.scaled_verts_from_bbox_gen(bbox_list, theta_list)
        gid_list       = ut.flatten(gids_list)
        bbox_size_list = ut.take_column(bbox_list, [2, 3])
        newsize_list   = [target_size] * len(bbox_list)

        # Checks
        invalid_flags = [w == 0 or h == 0 for (w, h) in bbox_size_list]
        invalid_bboxes = ut.compress(bbox_list, invalid_flags)
        assert len(invalid_bboxes) == 0, 'invalid bboxes=%r' % (invalid_bboxes,)

        # Extract "masks"
        interpolation = cv2.INTER_LANCZOS4
        warpkw = dict(interpolation=interpolation)

        last_gid = None
        mask_list = []
        arg_list = list(zip(gid_list, newsize_list, verts_list))
        for tup in ut.ProgIter(arg_list, lbl='computing localization masks', bs=True):
            gid, new_size, vert_list = tup
            if gid != last_gid:
                img = ibs.get_image_imgdata(gid)
                last_gid = gid

            # Copy the image, mask out the patch
            img_ = np.copy(img)
            vert_list_ = np.array(vert_list, dtype=np.int32 )
            cv2.fillConvexPoly(img_, vert_list_, (128, 128, 128))

            # Resize the image
            mask = cv2.resize(img_, tuple(new_size), **warpkw)
            # cv2.imshow('', mask)
            # cv2.waitKey()
            msg = 'Chip shape %r does not agree with target size %r' % (mask.shape, target_size, )
            assert mask.shape[0] == target_size[0] and mask.shape[1] == target_size[1], msg
            mask_list.append(mask)
    else:
        target_size_list = [target_size] * len(bboxes_list)
        img_list = [ibs.get_image_imgdata(gid) for gid in gid_list_]
        arg_iter = list(zip(gid_list_, img_list, bboxes_list, thetas_list,
                            target_size_list))
        result_list = ut.util_parallel.generate(get_localization_masks_worker, arg_iter,
                                                ordered=True)
        # Compute results
        result_list = list(result_list)
        # Extract results
        gids_list = ut.take_column(result_list, 0)
        chips_list = ut.take_column(result_list, 1)
        # Explicitly garbage collect large list of chips
        result_list = None
        # Flatten results
        gid_list = ut.flatten(gids_list)
        chip_list = ut.flatten(chips_list)
        assert len(gid_list) == len(chip_list)

    return gid_list_, gid_list, mask_list


ChipListImgType = dtool.ExternType(
    ut.partial(ut.load_cPkl, verbose=False),
    ut.partial(ut.save_cPkl, verbose=False),
    extkey='ext'
)


class Chip2Config(dtool.Config):
    _param_info_list = [
        ut.ParamInfo('localization_chip_target_size', (128, 128)),
        ut.ParamInfo('localization_chip_masking', False),
    ]
    _sub_config_list = [
        ThumbnailConfig
    ]


@register_preproc(
    tablename='localizations_chips', parents=['localizations'],
    colnames=['chips'],
    coltypes=[ChipListImgType],
    configclass=Chip2Config,
    fname='chipcache4',
    chunksize=128,
)
def compute_localizations_chips(depc, loc_id_list, config=None):
    r"""
    Extracts the detections for a given input image

    Args:
        depc (ibeis.depends_cache.DependencyCache):
        loc_id_list (list):  list of localization rowids
        config (dict): (default = None)

    Yields:
        (float, str): tup

    CommandLine:
        ibeis compute_localizations_chips

    Example:
        >>> # DISABLE_DOCTEST
        >>> from ibeis.core_images import *  # NOQA
        >>> import ibeis
        >>> defaultdb = 'PZ_MTEST'
        >>> ibs = ibeis.opendb(defaultdb=defaultdb)
        >>> depc = ibs.depc_image
        >>> gid_list = ibs.get_valid_gids()[0:8]
        >>> config = {'algo': '_COMBINED', 'localization_chip_masking': True}
        >>> # depc.delete_property('localizations_chips', gid_list, config=config)
        >>> results = depc.get_property('localizations_chips', gid_list, None, config=config)
        >>> print(results)
        >>> config = {'algo': '_COMBINED', 'localization_chip_masking': False}
        >>> # depc.delete_property('localizations_chips', gid_list, config=config)
        >>> results = depc.get_property('localizations_chips', gid_list, None, config=config)
        >>> print(results)
    """
    print('[ibs] Process Localization Chips')
    print('config = %r' % (config,))
    # Get controller
    ibs = depc.controller

    masking = config['localization_chip_masking']
    target_size = config['localization_chip_target_size']
    target_size_list = [target_size] * len(loc_id_list)

    gid_list_ = depc.get_ancestor_rowids('localizations', loc_id_list, 'images')
    assert len(gid_list_) == len(loc_id_list)

    # Grab the localizations
    bboxes_list = depc.get_native('localizations', loc_id_list, 'bboxes')
    thetas_list = depc.get_native('localizations', loc_id_list, 'thetas')
    len_list = [len(bbox_list) for bbox_list in bboxes_list]
    avg = sum(len_list) / len(len_list)
    args = (len(loc_id_list), min(len_list), avg, max(len_list), sum(len_list), )

    # Create image iterator
    img_list = (ibs.get_image_imgdata(gid) for gid in gid_list_)

    if masking:
        print('Extracting %d localization masks (min: %d, avg: %0.02f, max: %d, total: %d)' % args)
        worker_func = get_localization_masks_worker
    else:
        print('Extracting %d localization chips (min: %d, avg: %0.02f, max: %d, total: %d)' % args)
        worker_func = get_localization_chips_worker

    arg_iter = zip(gid_list_, img_list, bboxes_list, thetas_list, target_size_list)
    result_list = ut.util_parallel.generate(worker_func, arg_iter, ordered=True,
                                            nTasks=len(gid_list_), force_serial=True)

    # Return the results
    for gid, chip_list in result_list:
        ret_tuple = (
            chip_list,
        )
        yield ret_tuple


class Classifier2Config(dtool.Config):
    _param_info_list = [
        ut.ParamInfo('classifier_algo', 'cnn', valid_values=['cnn', 'svm']),
        ut.ParamInfo('classifier_weight_filepath', None),
        ut.ParamInfo('classifier_masking', False, hideif=False),  # True will classify localization chip as whole-image, False will classify whole image with localization masked out.
    ]
    _sub_config_list = [
        ThumbnailConfig,
    ]


@register_preproc(
    tablename='localizations_classifier', parents=['localizations'],
    colnames=['score', 'class'],
    coltypes=[np.ndarray, np.ndarray],
    configclass=Classifier2Config,
    fname='detectcache',
    chunksize=16,
)
def compute_localizations_classifications(depc, loc_id_list, config=None):
    r"""
    Extracts the detections for a given input image

    Args:
        depc (ibeis.depends_cache.DependencyCache):
        loc_id_list (list):  list of localization rowids
        config (dict): (default = None)

    Yields:
        (float, str): tup

    CommandLine:
        ibeis compute_localizations_classifications

    Example:
        >>> # DISABLE_DOCTEST
        >>> from ibeis.core_images import *  # NOQA
        >>> import ibeis
        >>> defaultdb = 'PZ_MTEST'
        >>> ibs = ibeis.opendb(defaultdb=defaultdb)
        >>> depc = ibs.depc_image
        >>> gid_list = ibs.get_valid_gids()[0:8]
        >>> config = {'algo': 'yolo'}
        >>> # depc.delete_property('localizations_classifier', gid_list, config=config)
        >>> results = depc.get_property('localizations_classifier', gid_list, None, config=config)
        >>> print(results)
        >>> config = {'algo': 'yolo', 'classifier_masking': True}
        >>> # depc.delete_property('localizations_classifier', gid_list, config=config)
        >>> results = depc.get_property('localizations_classifier', gid_list, None, config=config)
        >>> print(results)
        >>>
        >>> depc = ibs.depc_image
        >>> gid_list = list(set(ibs.get_imageset_gids(ibs.get_imageset_imgsetids_from_text('TEST_SET'))))
        >>> config = {'algo': '_COMBINED', 'classifier_algo': 'svm', 'classifier_weight_filepath': None}
        >>> # depc.delete_property('localizations_classifier', gid_list, config=config)
        >>> results = depc.get_property('localizations_classifier', gid_list, None, config=config)
        >>> print(results)
        >>>
        >>> config = {'algo': '_COMBINED', 'classifier_algo': 'svm', 'classifier_weight_filepath': 'localizer-zebra-10'}
        >>> # depc.delete_property('localizations_classifier', gid_list, config=config)
        >>> results = depc.get_property('localizations_classifier', gid_list, None, config=config)
        >>> print(results)
        >>>
        >>> config = {'algo': '_COMBINED', 'classifier_algo': 'svm', 'classifier_weight_filepath': 'localizer-zebra-50'}
        >>> results = depc.get_property('localizations_classifier', gid_list, None, config=config)
        >>> print(results)
        >>>
        >>> config = {'algo': '_COMBINED', 'classifier_algo': 'svm', 'classifier_weight_filepath': 'localizer-zebra-100'}
        >>> results = depc.get_property('localizations_classifier', gid_list, None, config=config)
        >>> print(results)
    """
    print('[ibs] Process Localization Classifications')
    print('config = %r' % (config,))
    # Get controller
    ibs = depc.controller

    masking = config.get('classifier_masking', False)

    # Get the results from the algorithm
    if config['classifier_algo'] in ['cnn']:
        if masking:
            gid_list_, gid_list, thumbnail_list = get_localization_masks(ibs, loc_id_list,
                                                                         target_size=(192, 192))
        else:
            gid_list_, gid_list, thumbnail_list = get_localization_chips(ibs, loc_id_list,
                                                                         target_size=(192, 192))

        # Generate thumbnail classifications
        result_list = ibs.generate_thumbnail_class_list(thumbnail_list, **config)

        # Assert the length is the same
        assert len(gid_list) == len(result_list)

        # Release thumbnails
        thumbnail_list = None

        # Group the results
        group_dict = {}
        for gid, result in zip(gid_list, result_list):
            if gid not in group_dict:
                group_dict[gid] = []
            group_dict[gid].append(result)
        assert len(gid_list_) == len(group_dict.keys())

        if masking:
            # We need to perform a difference calculation to see how much the masking
            # caused a deviation from the un-masked image
            config_ = dict(config)
            key_list = ['thumbnail_cfg', 'classifier_masking']
            for key in key_list:
                config_.pop(key)
            class_list_ = depc.get_property('classifier', gid_list_, 'class', config=config_)
            score_list_ = depc.get_property('classifier', gid_list_, 'score', config=config_)
        else:
            class_list_ = [None] * len(gid_list_)
            score_list_ = [None] * len(gid_list_)

        # Return the results
        for gid, class_, score_ in zip(gid_list_, class_list_, score_list_):
            result_list = group_dict[gid]
            zipped_list = list(zip(*result_list))
            score_list = np.array(zipped_list[0])
            class_list = np.array(zipped_list[1])
            if masking:
                score_ = score_ if class_ == 'positive' else 1.0 - score_
                score_list = score_ - score_list
                class_list = np.array(['positive'] * len(score_list))
            # Return tuple values
            ret_tuple = (
                score_list,
                class_list,
            )
            yield ret_tuple
    elif config['classifier_algo'] in ['svm']:
        assert not masking
        from ibeis.algo.detect.svm import classify
        # From localizations get gids
        config_ = {
            'algo': '_COMBINED',
            'feature2_algo': 'resnet',
        }
        gid_list_ = depc.get_ancestor_rowids('localizations', loc_id_list, 'images')
        assert len(gid_list_) == len(loc_id_list)

        # Get features
        vectors_list = depc.get_property('localizations_features', gid_list_, 'vector', config=config_)
        vectors_list_ = np.vstack(vectors_list)
        # Get gid_list
        shape_list = [ vector_list.shape[0] for vector_list in vectors_list ]
        gids_list = [ [gid_] * shape for gid_, shape in zip(gid_list_, shape_list) ]
        gid_list = ut.flatten(gids_list)

        # Stack vectors and classify
        classifier_weight_filepath = config['classifier_weight_filepath']
        result_list = classify(vectors_list_, weight_filepath=classifier_weight_filepath,
                               verbose=True)

        # Group the results
        score_dict = {}
        class_dict = {}
        for index, (gid, result) in enumerate(zip(gid_list, result_list)):
            if gid not in score_dict:
                score_dict[gid] = []
            if gid not in class_dict:
                class_dict[gid] = []
            score_, class_ = result
            score_dict[gid].append(score_)
            class_dict[gid].append(class_)
        assert len(gid_list_) == len(score_dict.keys())
        assert len(gid_list_) == len(class_dict.keys())

        for gid_ in gid_list_:
            score_list = score_dict[gid_]
            class_list = class_dict[gid_]
            ret_tuple = (
                np.array(score_list),
                np.array(class_list),
            )
            yield ret_tuple


class Feature2Config(dtool.Config):
    _param_info_list = [
        ut.ParamInfo('feature2_algo', 'vgg16', valid_values=['vgg', 'vgg16', 'vgg19', 'resnet', 'inception']),
        ut.ParamInfo('flatten', True),
    ]
    _sub_config_list = [
        ThumbnailConfig
    ]


@register_preproc(
    tablename='localizations_features', parents=['localizations'],
    colnames=['vector'],
    coltypes=[np.ndarray],
    configclass=Feature2Config,
    fname='featcache',
    chunksize=4,
)
def compute_localizations_features(depc, loc_id_list, config=None):
    r"""
    Computes features on images using pre-trained state-of-the-art models in
    Keras

    Args:
        depc (ibeis.depends_cache.DependencyCache):
        gid_list (list):  list of image rowids
        config (dict): (default = None)

    Yields:
        (np.ndarray, ): tup

    CommandLine:
        ibeis compute_localizations_features

    CommandLine:
        python -m ibeis.core_images compute_localizations_features --show

    Example:
        >>> # DISABLE_DOCTEST
        >>> from ibeis.core_images import *  # NOQA
        >>> import ibeis
        >>> defaultdb = 'PZ_MTEST'
        >>> ibs = ibeis.opendb(defaultdb=defaultdb)
        >>> depc = ibs.depc_image
        >>> print(depc.get_tablenames())
        >>> gid_list = ibs.get_valid_gids()[:16]
        >>> config = {'feature2_algo': 'vgg16', 'algo': '_COMBINED'}
        >>> depc.delete_property('localizations_features', gid_list, config=config)
        >>> features = depc.get_property('localizations_features', gid_list, 'vector', config=config)
        >>> print(features)
        >>> config = {'feature2_algo': 'vgg19', 'algo': '_COMBINED'}
        >>> depc.delete_property('localizations_features', gid_list, config=config)
        >>> features = depc.get_property('localizations_features', gid_list, 'vector', config=config)
        >>> print(features)
        >>> config = {'feature2_algo': 'resnet', 'algo': '_COMBINED'}
        >>> depc.delete_property('localizations_features', gid_list, config=config)
        >>> features = depc.get_property('localizations_features', gid_list, 'vector', config=config)
        >>> print(features)
        >>> config = {'feature2_algo': 'inception', 'algo': '_COMBINED'}
        >>> depc.delete_property('localizations_features', gid_list, config=config)
        >>> features = depc.get_property('localizations_features', gid_list, 'vector', config=config)
        >>> print(features)
    """
    from PIL import Image
    from keras.preprocessing import image as preprocess_image

    print('[ibs] Preprocess Features')
    print('config = %r' % (config,))
    # Get controller
    ibs = depc.controller
    target_size = (224, 224)
    ######################################################################################
    if config['feature2_algo'] in ['vgg', 'vgg16']:
        from keras.applications.vgg16 import VGG16 as MODEL_CLASS
        from keras.applications.vgg16 import preprocess_input
    ######################################################################################
    elif config['feature2_algo'] in ['vgg19']:
        from keras.applications.vgg19 import VGG19 as MODEL_CLASS
        from keras.applications.vgg19 import preprocess_input
    ######################################################################################
    elif config['feature2_algo'] in ['resnet']:
        from keras.applications.resnet50 import ResNet50 as MODEL_CLASS  # NOQA
        from keras.applications.resnet50 import preprocess_input
    ######################################################################################
    elif config['feature2_algo'] in ['inception']:
        from keras.applications.inception_v3 import InceptionV3 as MODEL_CLASS  # NOQA
        from keras.applications.inception_v3 import preprocess_input
        target_size = (299, 299)
    ######################################################################################
    else:
        raise ValueError('specified feature algo is not supported in config = %r' % (config, ))

    # Load chips
    gid_list_, gid_list, thumbnail_list = get_localization_chips(ibs, loc_id_list,
                                                                 target_size=target_size)

    # Build model
    model = MODEL_CLASS(include_top=False)

    # Define Preprocess
    def _preprocess(thumbnail):
        thumbnail = cv2.cvtColor(thumbnail, cv2.COLOR_BGR2RGB)
        image = Image.fromarray(thumbnail)
        # Process PIL image
        image_array = preprocess_image.img_to_array(image)
        image_array = np.expand_dims(image_array, axis=0)
        image_array = preprocess_input(image_array)
        return image_array

    thumbnail_iter = ut.ProgIter(thumbnail_list, lbl='preprocessing chips', bs=True)
    image_array = [
        _preprocess(thumbnail)
        for thumbnail in thumbnail_iter
    ]
    # Release thumbnails
    thumbnail_list = None

    inference_iter = ut.ProgIter(image_array, lbl='forward inference', bs=True)
    result_list = [
        model.predict(image_array_)
        for image_array_ in inference_iter
    ]

    # Release image_array
    image_array = None

    # Group the results
    group_dict = {}
    for gid, result in zip(gid_list, result_list):
        if gid not in group_dict:
            group_dict[gid] = []
        group_dict[gid].append(result)
    assert len(gid_list_) == len(group_dict.keys())

    # Return the results
    group_iter = ut.ProgIter(gid_list_, lbl='grouping results', bs=True)
    for gid in group_iter:
        result_list = group_dict[gid]
        if config['flatten']:
            result_list = [_.flatten() for _ in result_list]
        result_list = np.vstack(result_list)
        # Return tuple values
        ret_tuple = (result_list, )
        yield ret_tuple


class LabelerConfig(dtool.Config):
    _param_info_list = [
        ut.ParamInfo('labeler_weight_filepath', None),
    ]


@register_preproc(
    tablename='localizations_labeler', parents=['localizations'],
    colnames=['score', 'species', 'viewpoint', 'quality', 'orientation', 'probs'],
    coltypes=[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, list],
    configclass=LabelerConfig,
    fname='detectcache',
    chunksize=128,
)
def compute_localizations_labels(depc, loc_id_list, config=None):
    r"""
    Extracts the detections for a given input image

    Args:
        depc (ibeis.depends_cache.DependencyCache):
        loc_id_list (list):  list of localization rowids
        config (dict): (default = None)

    Yields:
        (float, str): tup

    CommandLine:
        ibeis compute_localizations_labels

    Example:
        >>> # DISABLE_DOCTEST
        >>> from ibeis.core_images import *  # NOQA
        >>> import ibeis
        >>> defaultdb = 'PZ_MTEST'
        >>> ibs = ibeis.opendb(defaultdb=defaultdb)
        >>> depc = ibs.depc_image
        >>> gid_list = ibs.get_valid_gids()[0:100]
        >>> depc.delete_property('labeler', gid_list)
        >>> results = depc.get_property('labeler', gid_list, None)
        >>> results = depc.get_property('labeler', gid_list, 'species')
        >>> print(results)
    """
    print('[ibs] Process Localization Labels')
    print('config = %r' % (config,))
    # Get controller
    ibs = depc.controller

    gid_list_, gid_list, chip_list = get_localization_chips(ibs, loc_id_list,
                                                            target_size=(128, 128))

    # Get the results from the algorithm
    result_list = ibs.generate_chip_label_list(chip_list, **config)
    assert len(gid_list) == len(result_list)

    # Release chips
    chip_list = None

    # Group the results
    group_dict = {}
    for gid, result in zip(gid_list, result_list):
        if gid not in group_dict:
            group_dict[gid] = []
        group_dict[gid].append(result)
    assert len(gid_list_) == len(group_dict.keys())

    # Return the results
    for gid in gid_list_:
        result_list = group_dict[gid]
        zipped_list = list(zip(*result_list))
        ret_tuple = (
            np.array(zipped_list[0]),
            np.array(zipped_list[1]),
            np.array(zipped_list[2]),
            np.array(zipped_list[3]),
            np.array(zipped_list[4]),
            list(zipped_list[5]),
        )
        yield ret_tuple


class DetectorConfig(dtool.Config):
    _param_info_list = [
        # ut.ParamInfo('classifier_sensitivity',    0.82),
        ut.ParamInfo('classifier_sensitivity',    0.01),
        ut.ParamInfo('classifier_weight_filepath', None),
        ut.ParamInfo('localizer_config_filepath', None),
        ut.ParamInfo('localizer_weight_filepath', None),
        ut.ParamInfo('localizer_grid',            False),
        # ut.ParamInfo('localizer_sensitivity',     0.16),
        ut.ParamInfo('localizer_sensitivity',     0.10),
        # ut.ParamInfo('labeler_sensitivity',       0.42),
        ut.ParamInfo('labeler_sensitivity',       0.10),
        ut.ParamInfo('labeler_weight_filepath', None),
    ]
    _sub_config_list = [
        ThumbnailConfig,
        LocalizerConfig,
    ]


@register_preproc(
    tablename='detections', parents=['images'],
    colnames=['score', 'bboxes', 'thetas', 'species', 'viewpoints', 'confs'],
    coltypes=[float, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray],
    configclass=DetectorConfig,
    fname='detectcache',
    chunksize=1024,
)
def compute_detections(depc, gid_list, config=None):
    r"""
    Extracts the detections for a given input image

    Args:
        depc (ibeis.depends_cache.DependencyCache):
        gid_list (list):  list of image rowids
        config (dict): (default = None)

    Yields:
        (float, np.ndarray, np.ndarray, np.ndarray, np.ndarray): tup

    CommandLine:
        ibeis compute_detections

    Example:
        >>> # SLOW_DOCTEST
        >>> from ibeis.core_images import *  # NOQA
        >>> import ibeis
        >>> defaultdb = 'PZ_MTEST'
        >>> ibs = ibeis.opendb(defaultdb=defaultdb)
        >>> # dbdir = '/Users/bluemellophone/Desktop/GGR-IBEIS-TEST/'
        >>> # dbdir = '/media/danger/GGR/GGR-IBEIS-TEST/'
        >>> # ibs = ibeis.opendb(dbdir=dbdir)
        >>> depc = ibs.depc_image
        >>> gid_list = ibs.get_valid_gids()[0:2]
        >>> depc.delete_property('detections', gid_list)
        >>> detects = depc.get_property('detections', gid_list, None)
        >>> print(detects)
    """
    from ibeis.web.apis_detect import USE_LOCALIZATIONS
    print('[ibs] Preprocess Detections')
    print('config = %r' % (config,))
    # Get controller
    ibs = depc.controller
    ibs.assert_valid_gids(gid_list)

    if not USE_LOCALIZATIONS:
        # Filter the gids by annotations
        prediction_list = depc.get_property('classifier', gid_list, 'class')
        confidence_list = depc.get_property('classifier', gid_list, 'score')
        confidence_list = [
            confidence if prediction == 'positive' else 1.0 - confidence
            for prediction, confidence  in zip(prediction_list, confidence_list)
        ]
        gid_list_ = [
            gid
            for gid, confidence in zip(gid_list, confidence_list)
            if confidence >= config['classifier_sensitivity']
        ]
    else:
        gid_list_ = list(gid_list)

    gid_set_ = set(gid_list_)
    # Get the localizations for the good gids and add formal annotations
    localizer_config = {
        'config_filepath' : config['localizer_config_filepath'],
        'weight_filepath' : config['localizer_weight_filepath'],
        'grid'            : config['localizer_grid'],
    }
    bboxes_list  = depc.get_property('localizations', gid_list_, 'bboxes',    config=localizer_config)
    thetas_list  = depc.get_property('localizations', gid_list_, 'thetas',    config=localizer_config)
    confses_list = depc.get_property('localizations', gid_list_, 'confs',     config=localizer_config)

    if not USE_LOCALIZATIONS:
        # depc.delete_property('labeler', gid_list_, config=localizer_config)
        specieses_list     = depc.get_property('labeler', gid_list_, 'species',   config=localizer_config)
        viewpoints_list    = depc.get_property('labeler', gid_list_, 'viewpoint', config=localizer_config)
        scores_list        = depc.get_property('labeler', gid_list_, 'score',     config=localizer_config)
    else:
        specieses_list     = depc.get_property('localizations', gid_list_, 'classes',   config=localizer_config)
        viewpoints_list    = [
            [-1] * len(bbox_list)
            for bbox_list in bboxes_list
        ]
        scores_list        = depc.get_property('localizations', gid_list_, 'confs',     config=localizer_config)

    # Collect the detections, filtering by the localization confidence
    empty_list = [0.0, np.array([]), np.array([]), np.array([]), np.array([]), np.array([])]
    detect_dict = {}
    for index, gid in enumerate(gid_list_):
        bbox_list = bboxes_list[index]
        theta_list = thetas_list[index]
        species_list = specieses_list[index]
        # species_dict = {}
        # for species in species_list:
        #     if species not in species_dict:
        #         species_dict[species] = 0
        #     species_dict[species] += 1
        # for tup in species_dict.iteritems():
        #     print('\t%r' % (tup, ))
        # print('----')
        viewpoint_list = viewpoints_list[index]
        conf_list = confses_list[index]
        score_list = scores_list[index]
        zipped = list(zip(bbox_list, theta_list, species_list, viewpoint_list,
                          conf_list, score_list))
        zipped = [
            [bbox, theta, species, viewpoint, conf * score]
            for bbox, theta, species, viewpoint, conf, score in zipped
            if conf >= config['localizer_sensitivity'] and score >= config['labeler_sensitivity'] and max(bbox[2], bbox[3]) / min(bbox[2], bbox[3]) < 20.0
        ]
        if len(zipped) == 0:
            detect_list = list(empty_list)
        else:
            detect_list = [0.0] + [np.array(_) for _ in zip(*zipped)]
        detect_dict[gid] = detect_list

    # Filter the annotations by the localizer operating point
    for gid in gid_list:
        if gid not in gid_set_:
            assert gid not in detect_dict
            result = list(empty_list)
        else:
            assert gid in detect_dict
            result = detect_dict[gid]
        # print(result)
        # raw_input()
        # print('')
        # image = ibs.get_image_imgdata(gid)
        # image = vt.resize(image, (500, 500))
        # cv2.imshow('', image)
        # cv2.waitKey(0)
        yield tuple(result)


if __name__ == '__main__':
    r"""
    CommandLine:
        python -m ibeis.core_images
        python -m ibeis.core_images --allexamples
    """
    import multiprocessing
    multiprocessing.freeze_support()  # for win32
    import utool as ut  # NOQA
    ut.doctest_funcs()
