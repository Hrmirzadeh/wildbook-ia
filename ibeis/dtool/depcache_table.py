# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals
import utool as ut
import six
from six.moves import zip, range
from os.path import join, exists
from dtool import base
from dtool import __SQLITE__ as lite
(print, rrr, profile) = ut.inject2(__name__, '[depcache_table]')


EXTERN_SUFFIX = '_extern_uri'

CONFIG_TABLE = 'config'
CONFIG_ROWID = 'config_rowid'
CONFIG_HASHID = 'config_hashid'


def ensure_config_table(db):
    config_addtable_kw = ut.odict(
        [
            ('tablename', CONFIG_TABLE,),
            ('coldef_list', [
                (CONFIG_ROWID, 'INTEGER PRIMARY KEY'),
                (CONFIG_HASHID, 'TEXT'),
            ],),
            ('docstr', 'table for algo configurations'),
            ('superkeys', [(CONFIG_HASHID,)]),
            ('dependson', [])
        ]
    )
    if not db.has_table(CONFIG_TABLE):
        db.add_table(**config_addtable_kw)


class DependencyCacheTable(object):
    """
    An individual node in the dependency graph.
    """

    def __init__(table, depc=None, parent_tablenames=None, tablename=None,
                 data_colnames=None, data_coltypes=None, preproc_func=None,
                 docstr='no docstr', fname=None, asobject=False,
                 chunksize=None, isalgo=False):

        table.fpath_to_db = {}

        table.parent_tablenames = parent_tablenames
        table.tablename = tablename
        table.data_colnames = tuple(data_colnames)
        table.data_coltypes = data_coltypes
        table.preproc_func = preproc_func

        table._internal_data_colnames = []
        table._internal_data_coltypes = []
        table._nested_idxs = []
        table.sqldb_fpath = None
        table.extern_read_funcs = {}
        table._nested_idxs2 = []
        table.isalgo = isalgo

        table.docstr = docstr
        table.fname = fname
        table.depc = depc
        table.db = None
        table.chunksize = None
        table._asobject = asobject
        table._update_internals()
        table._assert_self()

    def _assert_self(table):
        if table.preproc_func is not None:
            argspec = ut.get_func_argspec(table.preproc_func)
            args = argspec.args
            if argspec.varargs and argspec.keywords:
                assert len(args) == 1, 'varargs and kwargs must have one arg for depcache'
            else:
                if len(args) < 3:
                    print('args = %r' % (args,))
                    assert False, ('preproc func must have a depcache arg, at'
                                   ' least one parent rowid arg, and a config'
                                   ' arg')
                rowid_args = args[1:-1]
                if len(rowid_args) != len(table.parents):
                    print('table.preproc_func = %r' % (table.preproc_func,))
                    print('args = %r' % (args,))
                    print('rowid_args = %r' % (rowid_args,))
                    msg = (
                        ('preproc function for table=%s must have as many '
                         'rowids %d args as parents %d') % (
                            table.tablename, len(rowid_args), len(table.parents))
                    )
                    assert False, msg

    def _update_internals(table):
        extern_read_funcs = {}
        # TODO: can rewrite much of this
        internal_data_colnames = []
        internal_data_coltypes = []
        _nested_idxs2 = []

        nested_to_flat = {}

        external_to_internal = {}

        for colx, (colname, coltype) in enumerate(zip(table.data_colnames, table.data_coltypes)):
            if isinstance(coltype, tuple) or ut.is_func_or_method(coltype):
                if ut.is_func_or_method(coltype) or ut.is_func_or_method(coltype[0]) or coltype[0] == 'extern':
                    if isinstance(coltype, tuple):
                        if coltype[0] == 'extern':
                            read_func = coltype[1]
                        else:
                            read_func = coltype[0]
                    else:
                        read_func = coltype
                    extern_read_funcs[colname] = read_func
                    _nested_idxs2.append(len(internal_data_colnames))
                    intern_colname = colname + EXTERN_SUFFIX
                    internal_data_colnames.append(intern_colname)
                    internal_data_coltypes.append(lite.TYPE_TO_SQLTYPE[str])
                    external_to_internal[colname] = intern_colname
                else:
                    nest = []
                    table._nested_idxs.append(colx)
                    nested_to_flat[colname] = []
                    for count, dimtype in enumerate(coltype):
                        nest.append(len(internal_data_colnames))
                        flat_colname = '%s_%d' % (colname, count)
                        nested_to_flat[colname].append(flat_colname)
                        internal_data_colnames.append(flat_colname)
                        internal_data_coltypes.append(lite.TYPE_TO_SQLTYPE[dimtype])
                    _nested_idxs2.append(nest)
            else:
                _nested_idxs2.append(len(internal_data_colnames))
                internal_data_colnames.append(colname)
                internal_data_coltypes.append(lite.TYPE_TO_SQLTYPE[coltype])

        assert len(set(internal_data_colnames)) == len(internal_data_colnames)
        assert len(internal_data_coltypes) == len(internal_data_colnames)
        table.extern_read_funcs = extern_read_funcs
        table.external_to_internal = external_to_internal
        table.nested_to_flat = nested_to_flat
        table._nested_idxs2 = _nested_idxs2
        table._internal_data_colnames = tuple(internal_data_colnames)
        table._internal_data_coltypes = tuple(internal_data_coltypes)
        table._assert_self()

    def get_addtable_kw(table):
        primary_coldef = [(table.rowid_colname, 'INTEGER PRIMARY KEY')]
        parent_coldef = [(key, 'INTEGER NOT NULL') for key in table.parent_rowid_colnames]
        config_coldef = [(CONFIG_ROWID, 'INTEGER DEFAULT 0')]
        internal_data_coldef = list(zip(table._internal_data_colnames,
                                        table._internal_data_coltypes))

        coldef_list = primary_coldef + parent_coldef + config_coldef + internal_data_coldef
        add_table_kw = ut.odict([
            ('tablename', table.tablename,),
            ('coldef_list', coldef_list,),
            ('docstr', table.docstr,),
            ('superkeys', [table.superkey_colnames],),
            ('dependson', table.parents),
        ])
        return add_table_kw

    def initialize(table):
        table.db = table.depc.fname_to_db[table.fname]
        if not table.db.has_table(table.tablename):
            table.db.add_table(**table.get_addtable_kw())

    def print_schemadef(table):
        print('\n'.join(table.db.get_table_autogen_str(table.tablename)))

    def _get_all_rowids(table):
        pass

    @property
    def tabletype(table):
        return 'algo' if table.isalgo else 'node'

    @property
    def parents(table):
        return table.parent_tablenames

    @property
    def columns(table):
        return table.data_colnames

    @property
    def extern_columns(table):
        return list(table.external_to_internal.keys())

    @property
    def rowid_colname(table):
        return table.tablename + '_rowid'

    @property
    def parent_rowid_colnames(table):
        #return tuple([table.depc[parent].rowid_colname for parent in table.parents])
        return tuple([parent + '_rowid' for parent in table.parents])

    @property
    def superkey_colnames(table):
        return table.parent_rowid_colnames + (CONFIG_ROWID,)

    @property
    def _table_colnames(table):
        return table.superkey_colnames + table._internal_data_colnames

    def _custom_str(table):
        typestr = table.__class__.__name__
        custom_str = '<%s(%s) at %s>' % (typestr, table.tablename, hex(id(table)))
        return custom_str

    def __repr__(table):
        return table._custom_str()

    def __str__(table):
        return table._custom_str()

    # ---------------------------
    # --- CONFIGURATION TABLE ---
    # ---------------------------

    def get_config_rowid(table, config=None):
        config_rowid = table.add_config(config)
        return config_rowid

    def get_config_hashid(table, config_rowid_list):
        hashid_list = table.db.get(
            CONFIG_TABLE, (CONFIG_HASHID,), config_rowid_list,
            id_colname=CONFIG_ROWID)
        return hashid_list

    def get_config_rowid_from_hashid(table, config_hashid_list):
        config_rowid_list = table.db.get(
            CONFIG_TABLE, (CONFIG_ROWID,), config_hashid_list,
            id_colname=CONFIG_HASHID)
        return config_rowid_list

    def add_config(table, config):
        #config_hashid = config.get('feat_cfgstr')
        #assert config_hashid is not None
        # TODO store config_rowid in qparams
        #else:
        #    config_hashid = db.cfg.feat_cfg.get_cfgstr()
        if False:
            if config is not None:
                try:
                    #config_hashid = 'none'
                    config_hashid = config.get(table.tablename + '_hashid')
                except KeyError:
                    try:
                        subconfig = config.get(table.tablename + '_config')
                        config_hashid = ut.hashstr27(ut.to_json(subconfig))
                    except KeyError:
                        print('[deptbl.config] Warning: Config must either'
                              'contain a string <tablename>_hashid or a dict'
                              '<tablename>_config')
                        raise
            else:
                config_hashid = 'none'
        if isinstance(config, base.TableConfig):
            config_strid = config.get_cfgstr()
        elif isinstance(config, base.AlgoRequest):
            # config_strid = config.get_cfgstr()
            raise NotImplementedError('')
        else:
            config_strid = ut.to_json(config)
        config_hashid = ut.hashstr27(config_strid)
        if table.depc._debug:
            print('config_strid = %r' % (config_strid,))
            print('config_hashid = %r' % (config_hashid,))
        get_rowid_from_superkey = table.get_config_rowid_from_hashid
        config_rowid_list = table.db.add_cleanly(
            CONFIG_TABLE, (CONFIG_HASHID,), [(config_hashid,)],
            get_rowid_from_superkey)
        config_rowid = config_rowid_list[0]
        if table.depc._debug:
            print('config_rowid_list = %r' % (config_rowid_list,))
            print('config_rowid = %r' % (config_rowid,))
        return config_rowid

    # ----------------------
    # --- GETTERS NATIVE ---
    # ----------------------

    def _make_unnester(table):
        # TODO: rewrite
        nested_nCols = len(table.data_colnames)
        idxs1 = table._nested_idxs
        mask1 = ut.index_to_boolmask(idxs1, nested_nCols)
        mask2 = ut.not_list(mask1)
        idxs2 = ut.where(mask2)
        def unnest_data(data):
            unnested_cols = list(zip(ut.take(data, idxs2)))
            nested_cols = ut.take(data, idxs1)
            grouped_items = [nested_cols, unnested_cols]
            groupxs = [idxs1, idxs2]
            unflat = ut.ungroup(grouped_items, groupxs,
                                nested_nCols - 1)
            return tuple(ut.flatten(unflat))
        # Hack when a sql schema has tuples defined in it
        return unnest_data

    def _concat_rowids_data(table, dirty_parent_rowids, proptup_gen, config_rowid):
        for parent_rowids, data_cols in zip(dirty_parent_rowids, proptup_gen):
            try:
                yield parent_rowids + (config_rowid,) + data_cols
            except Exception as ex:
                ut.printex(ex, 'cat error', keys=[
                    'config_rowid', 'data_cols', 'parent_rowids'])
                raise

    def _concat_rowids_algo_result(table, dirty_parent_rowids, proptup_gen, config_rowid):
        # TODO: generalize to all external data that needs to be written
        # explicitly
        extern_fname_list = table._get_extern_fnames(dirty_parent_rowids, config_rowid)
        extern_dpath = table._get_extern_dpath()
        ut.ensuredir(extern_dpath, verbose=True or table.depc._debug)
        fpath_list = [join(extern_dpath, fname) for fname in extern_fname_list]
        for parent_rowids, algo_result, extern_fpath in zip(dirty_parent_rowids, proptup_gen, fpath_list):
            try:
                algo_result.save_to_fpath(extern_fpath, True)
                yield parent_rowids + (config_rowid,) + (extern_fpath,)
            except Exception as ex:
                ut.printex(ex, 'cat2 error', keys=[
                    'config_rowid', 'data_cols', 'parent_rowids'])
                raise

    def _get_extern_dpath(table):
        cache_dpath = table.depc.cache_dpath
        extern_dname = 'extern_' + table.tablename
        extern_dpath = join(cache_dpath, extern_dname)
        return extern_dpath

    def _get_extern_fnames(table, parent_rowids, config_rowid):
        # TODO: respect request objects
        # Only applies to algorithm tables
        config_hashid = table.get_config_hashid([config_rowid])[0]
        fmtstr = table.tablename + '_id={rowids}_{config_hashid}{ext}'
        fname_list = [fmtstr.format(rowids='_'.join(list(map(str, rowids))),
                                    config_hashid=config_hashid, ext='.cPkl')
                      for rowids in parent_rowids]
        return fname_list

    def _add_dirty_rows(table, dirty_parent_rowids, config_rowid, config, verbose=True):
        """ Does work of adding dirty rowids """
        try:
            args = zip(*dirty_parent_rowids)
            if table._asobject:
                # Convinience
                args = [table.depc.get_obj(parent, rowids)
                        for parent, rowids in zip(table.parents, args)]

            # CALL EXTERNAL PREPROCESSING / GENERATION FUNCTION
            proptup_gen = table.preproc_func(table.depc, *args, config=config)

            if len(table._nested_idxs) > 0:
                assert not table.isalgo
                unnest_data = table._make_unnester()
                proptup_gen = (unnest_data(data) for data in proptup_gen)

            if table.isalgo:
                dirty_params_iter = table._concat_rowids_algo_result(
                    dirty_parent_rowids, proptup_gen, config_rowid)
            else:
                dirty_params_iter = table._concat_rowids_data(
                    dirty_parent_rowids, proptup_gen, config_rowid)

            CHUNKED_ADD = table.chunksize is not None
            if CHUNKED_ADD:
                _iter = ut.ichunks(dirty_params_iter,
                                   chunksize=table.chunksize)
                for dirty_params_chunk in _iter:
                    table.db._add(table.tablename, table._table_colnames,
                                  dirty_params_chunk,
                                  nInput=len(dirty_params_chunk))
            else:
                nInput = len(dirty_parent_rowids)
                table.db._add(table.tablename, table._table_colnames,
                              dirty_params_iter, nInput=nInput)
        except Exception as ex:
            ut.printex(ex, 'error in add_rowids', keys=[
                'table',
                'table.parents',
                'parent_rowids',
                'config',
                'args',
                'config_rowid',
                'dirty_parent_rowids',
                'table.preproc_func'
            ])
            raise

    def add_rows_from_parent(table, parent_rowids, config=None, verbose=True):
        """
        Lazy addition
        """
        # Get requested configuration id
        config_rowid = table.get_config_rowid(config)
        # Find leaf rowids that need to be computed
        initial_rowid_list = table._get_rowid_from_superkey(parent_rowids,
                                                            config=config)
        if table.depc._debug:
            print('[deptbl.add] initial_rowid_list = %s' %
                  (ut.trunc_repr(initial_rowid_list),))
            print('[deptbl.add] config_rowid = %r' % (config_rowid,))
        # Get corresponding "dirty" parent rowids
        isdirty_list = ut.flag_None_items(initial_rowid_list)
        dirty_parent_rowids = ut.compress(parent_rowids, isdirty_list)
        num_dirty = len(dirty_parent_rowids)
        num_total = len(parent_rowids)
        if num_dirty > 0:
            with ut.Indenter('[ADD]', enabled=table.depc._debug):
                if verbose or table.depc._debug:
                    fmtstr = ('[deptbl.add] adding %d / %d new props to %r '
                              'for config_rowid=%r')
                    print(fmtstr % (num_dirty, num_total, table.tablename,
                                    config_rowid))
                table._add_dirty_rows(dirty_parent_rowids, config_rowid, config)
                # Get correct order, now that everything is clean in the database
                rowid_list = table._get_rowid_from_superkey(parent_rowids,
                                                            config=config)
        else:
            rowid_list = initial_rowid_list
        if table.depc._debug:
            print('[deptbl.add] rowid_list = %s' %
                  (ut.trunc_repr(rowid_list),))
        return rowid_list

    def get_rowid_from_superkey(table, parent_rowids, config=None, ensure=True,
                                eager=True, nInput=None, recompute=False):
        r"""
        get feat rowids of chip under the current state configuration
        if ensure is True, this function is equivalent to add_rows_from_parent

        Args:
            parent_rowids (list): list of tuples with the parent rowids as the
                value of each tuple
            config (None): (default = None)
            ensure (bool):  eager evaluation if True (default = True)
            eager (bool): (default = True)
            nInput (int): (default = None)
            recompute (bool): (default = False)

        Returns:
            list: rowid_list
        """
        if table.depc._debug:
            print('[deptbl.get_rowid] Lookup %s rowids from superkey with %d parents' % (
                table.tablename, len(parent_rowids)))
            print('[deptbl.get_rowid] config = %r' % (config,))
            print('[deptbl.get_rowid] ensure = %r' % (ensure,))
        #rowid_list = parent_rowids
        #return rowid_list

        if recompute:
            # get existing rowids, delete them, recompute the request
            rowid_list = table._get_rowid_from_superkey(
                parent_rowids, config=config, eager=eager, nInput=nInput)
            table.delete_rows(rowid_list)
            rowid_list = table.add_rows_from_parent(parent_rowids, config=config)
        elif ensure:
            rowid_list = table.add_rows_from_parent(parent_rowids, config=config)
        else:
            rowid_list = table._get_rowid_from_superkey(
                parent_rowids, config=config, eager=eager, nInput=nInput)
        return rowid_list

    def _get_rowid_from_superkey(table, parent_rowids, config=None, eager=True,
                                 nInput=None):
        """
        equivalent to get_rowid_from_superkey except ensure is constrained to be False.
        """
        colnames = (table.rowid_colname,)
        config_rowid = table.get_config_rowid(config=config)
        if table.depc._debug:
            print('_get_rowid_from_superkey')
            print('_get_rowid_from_superkey table.tablename = %r ' % (table.tablename,))
            print('_get_rowid_from_superkey parent_rowids = %s' % (ut.trunc_repr(parent_rowids)))
            print('_get_rowid_from_superkey config = %s' % (config))
            print('_get_rowid_from_superkey table.rowid_colname = %s' % (table.rowid_colname))
            print('_get_rowid_from_superkey config_rowid = %s' % (config_rowid))
        and_where_colnames = table.superkey_colnames
        params_iter = (rowids + (config_rowid,) for rowids in parent_rowids)
        params_iter = list(params_iter)
        #print('**params_iter = %r' % (params_iter,))
        rowid_list = table.db.get_where2(table.tablename, colnames, params_iter,
                                         and_where_colnames, eager=eager,
                                         nInput=nInput)
        if table.depc._debug:
            print('_get_rowid_from_superkey rowid_list = %s' % (ut.trunc_repr(rowid_list)))
        return rowid_list

    def delete_rows(table, rowid_list):
        #from dtool.algo.preproc import preproc_feat
        if table.on_delete is not None:
            table.on_delete()
        if ut.VERBOSE:
            print('deleting %d rows' % len(rowid_list))
        # Finalize: Delete table
        table.db.delete_rowids(table.tablename, rowid_list)
        num_deleted = len(ut.filter_Nones(rowid_list))
        return num_deleted

    def get_row_data(table, tbl_rowids, colnames=None):
        """
        colnames = ('mask', 'size')

        FIXME; unpacking is confusing with sql controller
        """
        if table.depc._debug:
            print('[deptbl.get_row_data] Get col of tablename=%r, colnames=%r with tbl_rowids=%s' %
                  (table.tablename, colnames, ut.trunc_repr(tbl_rowids)))
        try:
            request_unpack = False
            if colnames is None:
                resolved_colnames = table.data_colnames
                #table._internal_data_colnames
            else:
                if isinstance(colnames, six.text_type):
                    request_unpack = True
                    resolved_colnames = (colnames,)
                else:
                    resolved_colnames = colnames
            if table.depc._debug:
                print('[deptbl.get_row_data] resolved_colnames = %r' % (resolved_colnames,))

            eager = True
            nInput = None

            total = 0
            intern_colnames = []
            extern_resolve_colxs = []
            nesting_xs = []

            for c in resolved_colnames:
                if c in table.external_to_internal:
                    intern_colnames.append([table.external_to_internal[c]])
                    read_func = table.extern_read_funcs[c]
                    extern_resolve_colxs.append((total, read_func))
                    nesting_xs.append(total)
                    total += 1
                elif c in table.nested_to_flat:
                    nest = table.nested_to_flat[c]
                    nesting_xs.append(list(range(total, total + len(nest))))
                    intern_colnames.append(nest)
                    total += len(nest)
                else:
                    nesting_xs.append(total)
                    intern_colnames.append([c])
                    total += 1

            flat_intern_colnames = tuple(ut.flatten(intern_colnames))
            if table.depc._debug:
                print('[deptbl.get_row_data] flat_intern_colnames = %r' % (flat_intern_colnames,))

            # do sql read
            # FIXME: understand unpack_scalars and keepwrap
            raw_prop_list = table.get_internal_columns(
                tbl_rowids, flat_intern_colnames, eager, nInput,
                unpack_scalars=True, keepwrap=True)
            # unpack_scalars=not
            # request_unpack)
            # print('depth(raw_prop_list) = %r' % (ut.depth_profile(raw_prop_list),))

            prop_listT = list(zip(*raw_prop_list))
            for extern_colx, read_func in extern_resolve_colxs:
                data_list = []
                if table.depc._debug:
                    print('[deptbl.get_row_data] read_func = %r' % (read_func,))
                for uri in prop_listT[extern_colx]:
                    try:
                        # FIXME: only do this for a localpath
                        uri1 = join(table.depc.cache_dpath, uri)
                        data = read_func(uri1)
                    except Exception as ex:
                        ut.printex(ex, 'failed to load external data',
                                   iswarning=False,
                                   keys=[
                                       'uri',
                                       'uri1',
                                       (exists, 'uri1'),
                                       'read_func'])
                        raise
                        # FIXME
                        #data = None
                    data_list.append(data)
                prop_listT[extern_colx] = data_list

            nested_proplistT = ut.list_unflat_take(prop_listT, nesting_xs)

            for tx in ut.where([isinstance(xs, list) for xs in nesting_xs]):
                nested_proplistT[tx] = list(zip(*nested_proplistT[tx]))

            prop_list = list(zip(*nested_proplistT))

            if request_unpack:
                prop_list = [None if p is None else p[0] for p in prop_list]
        except Exception as ex:
            ut.printex(ex, 'failed in get col', keys=[
                'table.tablename',
                'request_unpack',
                'tbl_rowids',
                'colnames',
                'resolved_colnames',
                'raw_prop_list',
                (ut.depth_profile, 'raw_prop_list'),
                'prop_listT',
                (ut.depth_profile, 'prop_listT'),
                'nesting_xs',
                'nested_proplistT',
                'prop_list'])
            raise
        return prop_list

    def get_internal_columns(table, tbl_rowids, colnames=None, eager=True,
                             nInput=None, unpack_scalars=True, keepwrap=False):
        prop_list = table.db.get(
            table.tablename, colnames, tbl_rowids,
            id_colname=table.rowid_colname, eager=eager, nInput=nInput,
            unpack_scalars=unpack_scalars, keepwrap=keepwrap)
        return prop_list
