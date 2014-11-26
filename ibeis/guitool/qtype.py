from __future__ import absolute_import, division, print_function
#from guitool.__PYQT__.QtCore import Qt
#import six
from guitool.__PYQT__.QtCore import QLocale
import utool
import uuid
import numpy as np
from guitool.__PYQT__ import QtGui
from guitool.guitool_decorators import checks_qt_error
#if six.PY2:
#    from guitool.__PYQT__.QtCore import QString
#    from guitool.__PYQT__.QtCore import QVariant
#elif six.PY3:
QVariant = None
QString = str

(print, print_, printDBG, rrr, profile) = utool.inject(
    __name__, '[qtype]', DEBUG=False)


SIMPLE_CASTING = True


ItemDataRoles = {
    0  : 'DisplayRole',       # key data to be rendered in the form of text. (QString)
    1  : 'DecorationRole',     # data to be rendered as an icon. (QColor, QIcon or QPixmap)
    2  : 'EditRole',           # data in a form suitable for editing in an editor. (QString)
    3  : 'ToolTipRole',        # data displayed in the item's tooltip. (QString)
    4  : 'StatusTipRole',      # data displayed in the status bar. (QString)
    5  : 'WhatsThisRole',      # data displayed in "What's This?" mode. (QString)
    13 : 'SizeHintRole',       # size hint for item that will be supplied to views. (QSize)
    6  : 'FontRole',           # font used for items rendered with default delegate. (QFont)
    7  : 'TextAlignmentRole',  # text alignment of items with default delegate. (Qt::AlignmentFlag)
    8  : 'BackgroundRole',     # background brush for items with default delegate. (QBrush)
    9  : 'ForegroundRole',     # foreground brush for items rendered with default delegate. (QBrush)
    10 : 'CheckStateRole',     # checked state of an item. (Qt::CheckState)
    14 : 'InitialSortOrderRole',  # initial sort order of a header view (Qt::SortOrder).
    11 : 'AccessibleTextRole',    # text used by accessibility extensions and plugins (QString)
    12 : 'AccessibleDescriptionRole',  # accessibe description of the item for (QString)
    32 : 'UserRole',             # first role that can be used for application-specific purposes.
    8  : 'BackgroundColorRole',  # Obsolete. Use BackgroundRole instead.
    9  : 'TextColorRole',        # Obsolete. Use ForegroundRole instead.
}

LOCALE = QLocale()

# Custom types of data that can be displayed (usually be a delegate)
QT_PIXMAP_TYPES = set((QtGui.QPixmap, 'PIXMAP'))
QT_ICON_TYPES   = set((QtGui.QIcon, 'ICON'))
QT_BUTTON_TYPES = set(('BUTTON',))
QT_COMBO_TYPES = set(('COMBO',))


QT_IMAGE_TYPES  = set(list(QT_PIXMAP_TYPES) + list(QT_ICON_TYPES))
# A set of all delegate types
QT_DELEGATE_TYPES = set(list(QT_IMAGE_TYPES) + list(QT_BUTTON_TYPES) + list(QT_COMBO_TYPES))


def qindexinfo(index):
    variant = index.data()
    if SIMPLE_CASTING:
        item = str(variant)
    else:
        item = str(variant.toString())
    row  = index.row()
    col  = index.column()
    return (item, row, col)

#def format_float(data):
#    #argument_format = {
#    #    'e':    format as [-]9.9e[+|-]999
#    #    'E':    format as [-]9.9E[+|-]999
#    #    'f':    format as [-]9.9
#    #    'g':    use e or f format, whichever is the most concise
#    #    'G':    use E or f format, whichever is the most concise
#    #}
#    data = 1000000
#    print(utool.dict_str({
#        'out1': str(QString.number(float(data), format='g', precision=8))
#    }))

#    QLocale(QLocale.English).toString(123456789, 'f', 2)


def numpy_to_qpixmap(npimg):
    data = npimg.astype(np.uint8)
    (height, width) = npimg.shape[0:2]
    format_ = QtGui.QImage.Format_RGB888
    qimg    = QtGui.QImage(data, width, height, format_)
    qpixmap = QtGui.QPixmap.fromImage(qimg)
    return qpixmap


def numpy_to_qicon(npimg):
    qpixmap = numpy_to_qpixmap(npimg)
    qicon = QtGui.QIcon(qpixmap)
    return qicon


def locale_float(float_, precision=4):
    """
    References:
        http://qt-project.org/doc/qt-4.8/qlocale.html#toString-9
    """
    return LOCALE.toString(float(float_), format='g', precision=precision)


@profile
def cast_into_qt(data):
    """
    Casts python data into a representation suitable for QT (usually a string)
    """
    if SIMPLE_CASTING:
        if utool.is_str(data):
            return str(data)
        elif utool.is_float(data):
            #qnumber = QString.number(float(data), format='g', precision=8)
            return locale_float(data)
        elif utool.is_bool(data):
            return bool(data)
        elif  utool.is_int(data):
            return int(data)
        elif isinstance(data, uuid.UUID):
            return str(data)
        elif utool.isiterable(data):
            return ', '.join(map(str, data))
        else:
            return str(data)
    if utool.is_str(data):
        return str(data)
    elif utool.is_float(data):
        #qnumber = QString.number(float(data), format='g', precision=8)
        return locale_float(data)
    elif utool.is_bool(data):
        return bool(data)
    elif  utool.is_int(data):
        return int(data)
    elif isinstance(data, uuid.UUID):
        return str(data)
    elif utool.isiterable(data):
        return ', '.join(map(str, data))
    elif data is None:
        return 'None'
    else:
        return 'Unknown qtype: %r for data=%r' % (type(data), data)


#@profile
#def __cast_into_qt_py2(data):
#    """ Casts data to a QVariant """
#    if utool.is_str(data):
#        return QVariant(str(data)).toString()
#    if utool.is_float(data):
#        #qnumber = QString.number(float(data), format='g', precision=8)
#        return QVariant(LOCALE.toString(float(data), format='g', precision=8))
#    elif utool.is_bool(data):
#        return QVariant(bool(data)).toString()
#    elif  utool.is_int(data):
#        return QVariant(int(data)).toString()
#    elif isinstance(data, uuid.UUID):
#        return QVariant(str(data)).toString()
#    elif utool.isiterable(data):
#        return QVariant(', '.join(map(str, data))).toString()
#    elif data is None:
#        return QVariant('None').toString()
#    else:
#        return 'Unknown qtype: %r for data=%r' % (type(data), data)


@checks_qt_error
@profile
def cast_from_qt(var, type_=None):
    """ Casts a QVariant to data """
    if SIMPLE_CASTING:
        if var is None:
            return None
        if type_ is not None:
            reprstr = str(var)
            return utool.smart_cast(reprstr, type_)
        return var

    # TODO: sip api v2 should take care of this.
    #
    #printDBG('Casting var=%r' % (var,))
    #if var is None:
    #    return None
    #if type_ is not None and isinstance(var, QVariant):
    #    # Most cases will be qvariants
    #    reprstr = str(var.toString())
    #    data = utool.smart_cast(reprstr, type_)
    #elif isinstance(var, QVariant):
    #    if var.typeName() == 'bool':
    #        data = bool(var.toBool())
    #    if var.typeName() in ['QString', 'str']:
    #        data = str(var.toString())
    #elif isinstance(var, QString):
    #    data = str(var)
    #elif isinstance(var, list):
    #    data = var
    ##elif isinstance(var, (int, long, str, float)):
    #elif isinstance(var, six.string_types) or isinstance(var, six.integer_types):
    #    # comboboxes return ints
    #    data = var
    #else:
    #    raise ValueError('Unknown QtType: type(var)=%r, var=%r' %
    #                     (type(var), var))
    #return data


#@profile
#def cast_from_qt__PY2(var, type_=None):
#    """ Casts a QVariant to data """
#    #printDBG('Casting var=%r' % (var,))
#    if var is None:
#        return None
#    if type_ is not None and isinstance(var, QVariant):
#        # Most cases will be qvariants
#        reprstr = str(var.toString())
#        data = utool.smart_cast(reprstr, type_)
#    elif isinstance(var, QVariant):
#        if var.typeName() == 'bool':
#            data = bool(var.toBool())
#        if var.typeName() in ['QString', 'str']:
#            data = str(var.toString())
#    elif isinstance(var, QString):
#        data = str(var)
#    #elif isinstance(var, (int, long, str, float)):
#    elif isinstance(var, six.string_types) or isinstance(var, six.integer_types):
#        # comboboxes return ints
#        data = var
#    else:
#        raise ValueError('Unknown QtType: type(var)=%r, var=%r' %
#                         (type(var), var))
#    return data


def infer_coltype(column_list):
    """ Infer Column datatypes """
    try:
        coltype_list = [type(column_data[0]) for column_data in column_list]
    except Exception:
        coltype_list = [str] * len(column_list)
    return coltype_list


def to_qcolor(color):
    qcolor = QtGui.QColor(*color[0:3])
    return qcolor
