# -*- coding: utf-8 -*-

#    Copyright 2011-2014 Roderick Bovee
#
#    This file is part of Aston.
#
#    Aston is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    Aston is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with Aston.  If not, see <http://www.gnu.org/licenses/>.

"""
Model for handling display of open files.
"""
#pylint: disable=C0103

from __future__ import unicode_literals
from collections import OrderedDict
from PyQt4 import QtGui, QtCore
from aston.resources import resfile
from aston.qtgui.Fields import aston_fields, aston_groups, aston_field_opts
#from aston.qtgui.MenuOptions import peak_models
from aston.qtgui.TableModel import TableModel
from aston.database.Peak import Peak
from aston.database.Palette import Palette, PaletteRun, Plot


class PaletteTreeModel(TableModel):
    """
    Handles interfacing with QTreeView and other file-related duties.
    """
    def __init__(self, database=None, tree_view=None, master_window=None, \
                 *args):
        super(PaletteTreeModel, self).__init__(database, tree_view, \
                                               master_window, *args)
        self.active_palette = self.db.query(Palette).first()
        self.fields = self.active_palette.columns.split(',')

        # create a list with all of the root items in it
        q = self.db.query(PaletteRun)
        self._children = q.filter_by(palette=self.active_palette,
                                     enabled=True).all()
        self.reset()

        ##set up selections
        #tree_view.setSelectionBehavior(QtGui.QAbstractItemView.SelectRows)
        #tree_view.setSelectionMode(QtGui.QAbstractItemView.ExtendedSelection)
        ##TODO: this works, but needs to be detached when opening a new folder
        #tree_view.selectionModel().currentChanged.connect(self.itemSelected)
        ##tree_view.clicked.connect(self.itemSelected)

        ##set up key shortcuts
        #delAc = QtGui.QAction("Delete", tree_view, \
        #    shortcut=QtCore.Qt.Key_Backspace, triggered=self.delItemKey)
        #delAc = QtGui.QAction("Delete", tree_view, \
        #    shortcut=QtCore.Qt.Key_Delete, triggered=self.delItemKey)
        #tree_view.addAction(delAc)

        ##set up right-clicking
        tree_view.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        tree_view.customContextMenuRequested.connect(self.click_main)
        tree_view.header().setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        tree_view.header().customContextMenuRequested.connect( \
            self.click_head)
        tree_view.header().setStretchLastSection(False)

        ##set up drag and drop
        #tree_view.setDragEnabled(True)
        #tree_view.setAcceptDrops(True)
        #tree_view.setDragDropMode(QtGui.QAbstractItemView.DragDrop)
        #tree_view.dragMoveEvent = self.dragMoveEvent

        #keep us aware of column reordering
        self.tree_view.header().sectionMoved.connect(self.cols_changed)

        #deal with combo boxs in table
        self.combo_delegates = {}
        self.update_combo_cols()

        #add special editing support for the name column
        self.name_delegate = NameColDelegate()
        self.tree_view.setItemDelegateForColumn(self.fields.index('name'), \
                                                self.name_delegate)

        ##prettify
        tree_view.collapseAll()
        tree_view.setColumnWidth(0, 300)
        tree_view.setColumnWidth(1, 60)

    def dragMoveEvent(self, event):
        #TODO: files shouldn't be able to be under peaks
        #index = self.proxyMod.mapToSource(self.tree_view.indexAt(event.pos()))
        if event.mimeData().hasFormat('application/x-aston-file'):
            QtGui.QTreeView.dragMoveEvent(self.tree_view, event)
        else:
            event.ignore()

    def mimeTypes(self):
        types = QtCore.QStringList()
        types.append('text/plain')
        types.append('application/x-aston-file')
        return types

    def mimeData(self, indexList):
        data = QtCore.QMimeData()
        objs = [i.internalPointer() for i in indexList \
                if i.column() == 0]
        data.setText(self.items_as_csv(objs))

        id_lst = [str(o.db_id) for o in objs]
        data.setData('application/x-aston-file', ','.join(id_lst))
        return data

    def dropMimeData(self, data, action, row, col, parent):
        #TODO: drop files into library?
        #TODO: deal with moving objects between tables
        # i.e. copy from compounds table into file table
        fids = data.data('application/x-aston-file')
        if not parent.isValid():
            new_parent = self.db
        else:
            new_parent = parent.internalPointer()
        for db_id in [int(i) for i in fids.split(',')]:
            obj = self.db.object_from_id(db_id)
            if obj is not None:
                obj._parent = new_parent
        return True

    def supportedDropActions(self):
        return QtCore.Qt.MoveAction

    def data(self, index, role):
        fld = self.fields[index.column()]
        obj = index.internalPointer()
        rslt = None
        if type(obj) is PaletteRun:
            if role == QtCore.Qt.DisplayRole or role == QtCore.Qt.EditRole:
                if fld == 'name':
                    rslt = obj.run.name
            elif role == QtCore.Qt.DecorationRole and fld == 'name':
                loc = resfile('aston/qtgui', 'icons/file.png')
                rslt = QtGui.QIcon(loc)
        elif type(obj) is Plot:
            if fld == 'vis' and role == QtCore.Qt.CheckStateRole:
                #TODO: allow vis to be a plot number instead?
                if obj.vis > 0:
                    rslt = QtCore.Qt.Checked
                else:
                    rslt = QtCore.Qt.Unchecked
            elif role == QtCore.Qt.DisplayRole or role == QtCore.Qt.EditRole:
                if fld == 'name':
                    rslt = obj.name
                elif fld in ['style', 'color']:
                    if fld == 'style':
                        i = obj.style
                    elif fld == 'color':
                        i = obj.color
                    rslt = aston_field_opts[fld][i]
            elif role == QtCore.Qt.FontRole and fld == 'name':
                # strike out invalid plot names
                if not obj.is_valid:
                    rslt = QtGui.QFont()
                    rslt.setStrikeOut(True)
            #elif role == QtCore.Qt.DecorationRole and index.column() == 0:
            #    if not obj.is_valid:
            #        loc = resfile('aston/qtgui', 'icons/x.png')
            #        rslt = QtGui.QIcon(loc)
        elif type(obj) is Peak:
            if fld == 'vis' and role == QtCore.Qt.CheckStateRole:
                if obj.vis:
                    rslt = QtCore.Qt.Checked
                else:
                    rslt = QtCore.Qt.Unchecked
            elif role == QtCore.Qt.DisplayRole or role == QtCore.Qt.EditRole:
                if fld == 'name':
                    rslt = obj.name
                elif fld == 'color':
                    rslt = aston_field_opts[fld][obj.color]
                elif fld in {'p-type', 'p-model'}:
                    rslt = aston_field_opts[fld][obj.info.get(fld, 'none')]
                elif fld in {'p-model-fit'}:
                    rslt = obj.info['p-model-fit']
                elif fld in {'p-area', 'p-length', 'p-height', 'p-width', \
                             'p-pwhm', 'p-time'}:
                    rslt = str(getattr(obj, fld[2:])())
        #elif role == QtCore.Qt.DisplayRole or role == QtCore.Qt.EditRole:
        #    if fld == 'p-model' and f.db_type == 'peak':
        #        rpeakmodels = {peak_models[k]: k for k in peak_models}
        #        rslt = rpeakmodels.get(f.info[fld], 'None')
        #    else:
        #        rslt = f.info[fld]
        #elif role == QtCore.Qt.DecorationRole and index.column() == 0:
        #    #TODO: icon for method, compound
        #    fname = {'file': 'file.png', 'peak': 'peak.png', \
        #            'spectrum': 'spectrum.png'}
        #    loc = resfile('aston/ui', 'icons/' + fname.get(f.db_type, ''))
        #    rslt = QtGui.QIcon(loc)
        return rslt

    def headerData(self, col, orientation, role):
        if orientation == QtCore.Qt.Horizontal and \
          role == QtCore.Qt.DisplayRole:
            if self.fields[col] in aston_fields:
                return aston_fields[self.fields[col]]
            else:
                return self.fields[col]
        else:
            return None

    def setData(self, index, data, role):
        obj = index.internalPointer()
        if isinstance(obj, PaletteRun):
            # have to edit this in the TableFile
            return False

        try:  # python 2
            data = bytes(data.toUtf8()).decode('utf8')
        except:  # python 3
            data = str(data)
        col = self.fields[index.column()].lower()

        if col == 'vis':
            obj.vis = data == u'2'
        elif col == 'name':
            obj.name = data
            #TODO: split apart commas to make mulitple plots
        elif col in {'style', 'color'}:
            rev_dict = {str(v): k for k, v \
                        in aston_field_opts[col].items()}
            setattr(obj, col, rev_dict[data])
        elif col == 'p-model':
            rev_dict = {str(v): k for k, v \
                        in aston_field_opts[col].items()}
            obj.refit(rev_dict[data])
        #else:
        #    obj.info[col] = data

        if isinstance(obj, Plot):
            obj.is_valid = True

        if col == 'vis' and isinstance(obj, Plot):
            self.master_window.plot_data(update_bounds=True)
        else:
            self.master_window.plot_data(update_bounds=False)

        self.db.merge(obj)
        self.db.commit()
        self.dataChanged.emit(index, index)
        return True

    def flags(self, index):
        col = self.fields[index.column()]
        obj = index.internalPointer()
        dflags = QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable
        dflags |= QtCore.Qt.ItemIsDropEnabled
        if not index.isValid():
            return dflags
        dflags |= QtCore.Qt.ItemIsDragEnabled
        if col == 'vis' and isinstance(obj, (Plot, Peak)):
            dflags |= QtCore.Qt.ItemIsUserCheckable
        elif col.startswith('p-') and not isinstance(obj, Peak):
            if col in {'p-model', 'p-type'}:
                dflags |= QtCore.Qt.ItemIsEditable
        else:
            dflags |= QtCore.Qt.ItemIsEditable
        return dflags

    def has_run(self, run, enabled=False):
        q = self.db.query(PaletteRun)
        q = q.filter_by(run=run, palette=self.active_palette)
        if enabled:
            q = q.filter_by(enabled=True)
        return q.count() > 0

    def add_run(self, run):
        with self.add_rows(None, 1):
            if self.has_run(run):
                prun = self.db.query(PaletteRun).filter_by(run=run, \
                  palette=self.active_palette).one()
            else:
                prun = PaletteRun(run=run, palette=self.active_palette)
                self.db.add(prun)
            prun.enabled = True
            self._children.append(prun)
        for p in prun.plots:
            if p.vis:
                self.master_window.plot_data()
                break
        self.db.commit()

    def add_plot(self, objs):
        #TODO: update plot here?
        for obj in objs:
            with self.add_rows(obj, 1):
                plot = Plot(paletterun=obj)
                self.db.add(plot)
        self.db.commit()

    def del_run(self, run):
        #TODO: update fileTable checkbox; allows deleting from this table
        q = self.db.query(PaletteRun)
        prun = q.filter_by(run=run, palette=self.active_palette).first()
        with self.del_row(prun):
            self._children.remove(prun)
            prun.enabled = False
            #self.db.delete(pobj)
            #TODO: delete unassociated plots and peaks?

        for p in prun.plots:
            if p.vis:
                self.master_window.plot_data()
                break
        self.db.commit()

    def itemSelected(self):
        #TODO: update an info window?
        #remove the current spectrum
        self.master_window.plotter.clear_highlight()

        #remove all of the peak patches from the
        #main plot and add new ones in
        sel = self.returnSelObj()
        self.master_window.specplotter.libscans = []
        if sel is not None:
            if sel.db_type == 'file':
            #    self.master_window.plotter.clear_peaks()
            #    if sel.getInfo('vis') == 'y':
            #        self.master_window.plotter.add_peaks( \
            #            sel.getAllChildren('peak'))
                pass
            elif sel.db_type == 'peak':
                if sel.parent_of_type('file').info['vis'] == 'y':
                    self.master_window.plotter.draw_highlight_peak(sel)
            elif sel.db_type == 'spectrum':
                self.master_window.specplotter.libscans = [sel.data]
                self.master_window.specplotter.plot()
        objs_sel = len(self.returnSelObjs())
        self.master_window.show_status(str(objs_sel) + ' items selected')

    def cols_changed(self, *_):  # don't care about the args
        flds = [self.fields[self.tree_view.header().logicalIndex(fld)] \
                    for fld in range(len(self.fields))]
        self.active_palette.columns = ','.join(flds)
        self.db.merge(self.active_palette)
        self.db.commit()

    def click_main(self, point):
        index = self.proxyMod.mapToSource(self.tree_view.indexAt(point))
        menu = QtGui.QMenu(self.tree_view)
        #sel = self.returnSelFiles()

        def add_menu_opt(name, func, objs, menu):
            ac = menu.addAction(name, self.click_handler)
            ac.setData((func, objs))

        fts = [index.internalPointer()]
        if type(fts[0]) is PaletteRun:
            add_menu_opt(self.tr('Create Plot'),
                         self.add_plot, fts, menu)

        ##Things we can do with peaks
        #fts = [s for s in sel if s.db_type == 'peak']
        #if len(fts) > 0:
        #    self._add_menu_opt(self.tr('Create Spec.'), \
        #                       self.createSpec, fts, menu)
        #    self._add_menu_opt(self.tr('Merge Peaks'), \
        #                       self.merge_peaks, fts, menu)

        #fts = [s for s in sel if s.db_type in ('spectrum', 'peak')]
        #if len(fts) > 0:
        #    self._add_menu_opt(self.tr('Find in Lib'), \
        #                       self.find_in_lib, fts, menu)

        ###Things we can do with files
        ##fts = [s for s in sel if s.db_type == 'file']
        ##if len(fts) > 0:
        ##    self._add_menu_opt(self.tr('Copy Method'), \
        ##                       self.makeMethod, fts, menu)

        ##Things we can do with everything
        #if len(sel) > 0:
        #    self._add_menu_opt(self.tr('Delete Items'), \
        #                       self.delete_objects, sel, menu)
        #    #self._add_menu_opt(self.tr('Debug'), self.debug, sel)

        if not menu.isEmpty():
            menu.exec_(self.tree_view.mapToGlobal(point))

    def click_handler(self):
        func, objs = self.sender().data()
        func(objs)

    def delItemKey(self):
        self.delete_objects(self.returnSelObjs())

    def debug(self, objs):
        pks = [o for o in objs if o.db_type == 'peak']
        for pk in pks:
            x = pk.data[:, 0]
            y = pk.as_gaussian()
            plt = self.master_window.plotter.plt
            plt.plot(x, y, '-')
            self.master_window.plotter.canvas.draw()

    def merge_peaks(self, objs):
        from aston.Math.Integrators import merge_ions
        new_objs = merge_ions(objs)
        self.delete_objects([o for o in objs if o not in new_objs])

    def createSpec(self, objs):
        with self.db:
            for obj in objs:
                obj._children += [obj.as_spectrum()]

    def find_in_lib(self, objs):
        for obj in objs:
            if obj.db_type == 'peak':
                spc = obj.as_spectrum().data
            elif obj.db_type == 'spectrum':
                spc = obj.data
            lib_spc = self.master_window.cmpd_tab.db.find_spectrum(spc)
            if lib_spc is not None:
                obj.info['name'] = lib_spc.info['name']
                obj.save_changes()

    #def makeMethod(self, objs):
    #    self.master_window.cmpd_tab.addObjects(None, objs)

    def click_head(self, point):
        menu = QtGui.QMenu(self.tree_view)
        subs = OrderedDict()
        for n in aston_groups:
            subs[n] = QtGui.QMenu(menu)

        for fld in aston_fields:
            if fld == 'name':
                continue
            grp = fld.split('-')[0]
            if grp in subs:
                ac = subs[grp].addAction(aston_fields[fld], \
                  self.click_head_handler)
            else:
                ac = menu.addAction(aston_fields[fld], \
                  self.click_head_handler)
            ac.setData(fld)
            ac.setCheckable(True)
            if fld in self.fields:
                ac.setChecked(True)

        for grp in subs:
            ac = menu.addAction(aston_groups[grp])
            ac.setMenu(subs[grp])

        menu.exec_(self.tree_view.mapToGlobal(point))

    def click_head_handler(self):
        fld = str(self.sender().data())
        if fld == 'name':
            return
        if fld in self.fields:
            indx = self.fields.index(fld)
            self.beginRemoveColumns(QtCore.QModelIndex(), indx, indx)
            for i in range(len(self._children)):
                self.beginRemoveColumns( \
                  self.index(i, 0, QtCore.QModelIndex()), indx, indx)
            self.fields.remove(fld)
            for i in range(len(self._children) + 1):
                self.endRemoveColumns()
        else:
            cols = len(self.fields)
            self.beginInsertColumns(QtCore.QModelIndex(), cols, cols)
            for i in range(len(self._children)):
                self.beginInsertColumns( \
                  self.index(i, 0, QtCore.QModelIndex()), cols, cols)
            self.tree_view.resizeColumnToContents(len(self.fields) - 1)
            self.fields.append(fld)
            for i in range(len(self._children) + 1):
                self.endInsertColumns()
        self.update_combo_cols()
        self.cols_changed()
        #FIXME: selection needs to be updated to new col too?
        #self.tree_view.selectionModel().selectionChanged.emit()

    def update_obj(self, dbid, obj):
        if obj is None and dbid is None:
            self.master_window.show_status(self.tr('All Files Loaded'))
        elif obj is None:
            #TODO: delete files if they aren't present
            #c.execute('DELETE FROM files WHERE id=?', (dbid,))
            pass
        else:
            obj._parent = self.db

    def active_plot(self):
        """
        Returns the plot currently selected in the list.
        If that plot is not visible, return the topmost visible plot.
        Used for determing which spectra to display on right click, etc.
        """
        plot = self.returnSelObj()
        if plot is not None:
            if type(plot) is Plot:
                if plot.vis > 0 and plot.is_valid:
                    return plot

        dts = self.returnChkObjs()
        if len(dts) == 0:
            return None
        else:
            return dts[0]

    def returnChkObjs(self, node=None):
        """
        Returns the lines checked as visible in the file list.
        """
        if node is None:
            node = QtCore.QModelIndex()

        chkFiles = []
        for i in range(self.proxyMod.rowCount(node)):
            prjNode = self.proxyMod.index(i, 0, node)
            t = self.proxyMod.mapToSource(prjNode).internalPointer()
            if type(t) is Plot:
                if t.vis > 0 and t.is_valid:
                    chkFiles.append(t)
            if len(t._children) > 0:
                chkFiles += self.returnChkObjs(prjNode)
        return chkFiles

    def returnSelObj(self):
        """
        Returns the file currently selected in the file list.
        Used for determing which spectra to display on right click, etc.
        """
        tab_sel = self.tree_view.selectionModel()
        if not tab_sel.currentIndex().isValid:
            return

        ind = self.proxyMod.mapToSource(tab_sel.currentIndex())
        if ind.internalPointer() is None:
            return  # it doesn't exist
        return ind.internalPointer()

    def returnSelObjs(self, cls=None):
        """
        Returns the files currently selected in the file list.
        Used for displaying the peak list, etc.
        """
        tab_sel = self.tree_view.selectionModel()
        files = []
        for i in tab_sel.selectedRows():
            obj = i.model().mapToSource(i).internalPointer()
            if cls is None or type(obj) is cls:
                files.append(obj)
        return files

    def items_as_csv(self, itms, delim=',', incHeaders=True):
        flds = [self.fields[self.tree_view.header().logicalIndex(fld)] \
                for fld in range(len(self.fields))]
        row_lst = []
        block_col = ['vis']
        for i in itms:
            col_lst = [i.info[col] for col in flds \
                       if col not in block_col]
            row_lst.append(delim.join(col_lst))

        if incHeaders:
            try:  # for python 2
                flds = [unicode(aston_fields[i]) for i in flds \
                        if i not in ['vis']]
            except:  # for python 3
                flds = [aston_fields[i] for i in flds \
                        if i not in ['vis']]
            header = delim.join(flds) + '\n'
            table = '\n'.join(row_lst)
            return header + table


class NameColDelegate(QtGui.QItemDelegate):
    #def __init__(self, opts, *args):
    #    self.opts = opts
    #    super(ComboDelegate, self).__init__(*args)

    def get_opts(self, obj):
        #TODO: weed out events
        opts = [i.lstrip('#') for a in obj.paletterun.run.analyses \
                        for i in a.trace.split(',')]
        opts += ['tic']
        return opts

    def createEditor(self, parent, option, index):
        obj = index.model().mapToSource(index).internalPointer()
        if isinstance(obj, Plot):
            cmb = QtGui.QComboBox(parent)
            cmb.setEditable(True)
            cmb.addItems(self.get_opts(obj))
        else:
            cmb = QtGui.QLineEdit(parent)
        return cmb

    def setEditorData(self, editor, index):
        obj = index.model().mapToSource(index).internalPointer()
        if isinstance(obj, Plot):
            #txt = index.data(QtCore.Qt.EditRole)
            txt = obj.name
            opts = self.get_opts(obj)
            if txt in opts:
                editor.setCurrentIndex(opts.index(txt))
            else:
                editor.setEditText(txt)
        super(NameColDelegate, self).setEditorData(editor, index)

    def setModelData(self, editor, model, index):
        obj = index.model().mapToSource(index).internalPointer()
        if isinstance(obj, Plot):
            data = str(editor.currentText())
        elif isinstance(obj, Peak):
            data = str(editor.text())
        data = data.replace('+-', '±').replace('->', '→')
        model.setData(index, data, QtCore.Qt.EditRole)
