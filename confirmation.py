# -*- coding: utf-8 -*-
"""
/***************************************************************************
 Gisquick plugin
 Publish your projects into Gisquick application
 ***************************************************************************/
"""

import os
import shutil

# Import the PyQt and QGIS libraries
from qgis.core import QgsVectorDataProvider, QgsRasterDataProvider, QgsDataSourceUri
from qgis.PyQt.QtWidgets import QWizard, QFileDialog, QMessageBox, QApplication
from qgis.PyQt.QtCore import Qt

from .utils import opt_value, create_formatted_tree
from .wizard import WizardPage


class ConfirmationPage(WizardPage):

    def __init__(self, plugin, page):
        super(ConfirmationPage, self).__init__(plugin, page)
        page.setButtonText(QWizard.CancelButton, "Close")
        page.setButtonText(QWizard.FinishButton, "Publish")

    def initialize(self):
        if self.plugin.run_in_gislab:
            self._publish_dir_default = os.path.join(
                os.environ['HOME'],
                'Publish',
                os.environ['USER'],
                os.path.basename(
                    os.path.dirname(self.plugin.project.fileName())
                )
            )
        else:
            self._publish_dir_default = os.path.dirname(self.plugin.project.fileName())
        self._publish_dir = self._publish_dir_default
        self._datasources = {}

        self.dialog.text_publish_dir.setPlainText(self._publish_dir)
        self.dialog.button_publish_dir.clicked.connect(self.select_publish_dir)

    def select_publish_dir(self):
        self._publish_dir = str(QFileDialog.getExistingDirectory(self.dialog, "Select Directory"))
        if not self._publish_dir:
            self._publish_dir = self._publish_dir_default

        self.dialog.text_publish_dir.setPlainText(
            self._publish_dir
        )

    def project_files(self):
        # Project files overview
        publish_filename = os.path.normpath(os.path.splitext(self.plugin.project.fileName())[0])
        publish_timestamp = str(self.plugin.metadata['publish_date_unix'])
        project_filename = "{0}_{1}.qgs".format(
            publish_filename,
            publish_timestamp
        )
        metadata_filename = "{0}_{1}.meta".format(
            publish_filename,
            publish_timestamp
        )

        return project_filename, metadata_filename


    def validate(self):
        return self.copy_published_project()

    def copy_published_project(self):
        # create publish directory if not exists
        if not os.path.exists(self._publish_dir):
            os.makedirs(self._publish_dir)

        def copy_project_files(link=False):
            project_filename, metadata_filename = self.project_files()
            fn = os.symlink if link else shutil.copy
            try:
                for filename in (project_filename, metadata_filename):
                    outputname = os.path.join(
                        self._publish_dir,
                        os.path.basename(filename)
                    )
                    fn(filename, outputname)
            except (shutil.Error, IOError) as e:
                raise Exception("Copying project files failed: {0}".format(e))

        def copy_data_sources(link=False):
            messages = [] # error messages
            # overwrite enabled by default, don't ask user
            # overwrite = [] # files to overwrite
            project_dir = os.path.dirname(self.plugin.project.fileName())
            # collect files to be copied
            publish_files = {}
            for ds in list(self._datasources.values()):
                for dsfile in ds:
                    if os.path.exists(dsfile) and os.path.isfile(dsfile):
                        publish_path = os.path.dirname(self._publish_dir + dsfile[len(project_dir):])
                        if publish_path not in publish_files:
                            publish_files[publish_path] = []

                        if os.path.splitext(dsfile)[1] == '.shp':
                            # Esri Shapefile (copy all files)
                            shpname = os.path.splitext(dsfile)[0]
                            for shpext in ('shp', 'shx', 'dbf', 'sbn', 'sbx',
                                           'fbn', 'fbx', 'ain', 'aih', 'atx',
                                           'ixs', 'mxs', 'prj', 'xml', 'cpg'):
                                shpfile = '{0}.{1}'.format(shpname, shpext)
                                if os.path.exists(shpfile):
                                    dstfile = os.path.join(publish_path, shpfile)
                                    # if os.path.exists(dstfile):
                                    #     overwrite.append(dstfile)
                                    publish_files[publish_path].append(shpfile)
                        else:
                            # other formats (we expect one file per datasource)
                            dstfile = os.path.join(publish_path, os.path.basename(dsfile))
                            # if os.path.exists(dstfile):
                            #     overwrite.append(dstfile)
                            publish_files[publish_path].append(dsfile)
                    elif 'url' in dsfile.lower():
                        # skip OWS layers (ugly: assuming URL in data source)
                        continue
                    else:
                        messages.append("Unsupported data source: {0} is not a file".format(dsfile))

            # if overwrite:
            #     response = QMessageBox.question(self.dialog, "Overwrite",
            #                                     "Files:\n{0}\nalready exists. Do you want to overwrite them?".format(
            #                                         os.linesep.join(overwrite if len(overwrite) < 6 else overwrite[:5] + ['...'])
            #                                     ),
            #                                     QMessageBox.Yes, QMessageBox.No)
            #     if response == QMessageBox.Yes:
            #         overwrite = None

            # set busy cursor
            QApplication.setOverrideCursor(Qt.WaitCursor)
            # copy/link collected project files
            fn = os.symlink if link else shutil.copy
            for publish_dir, project_files in list(publish_files.items()):
                try:
                    # create dirs if not exists
                    if not os.path.exists(os.path.dirname(publish_path)):
                        os.makedirs(os.path.dirname(publish_path))
                    for dsfile in project_files:
                        # if overwrite:
                        #     # skip existing files
                        #     dstfile = os.path.join(publish_path, os.path.basename(dsfile))
                        #     if dstfile in overwrite:
                        #         continue
                        dstfile = os.path.join(
                            publish_path,
                            os.path.basename(dsfile)
                        )
                        # copy target only if doesn't exist or out-dated
                        if not os.path.exists(dstfile) or \
                           os.stat(dsfile).st_mtime > os.stat(dstfile).st_mtime:
                            # check if target directories exist
                            dirname = os.path.dirname(dstfile)
                            if not os.path.exists(dirname):
                                os.makedirs(dirname)
                            fn(dsfile, dstfile)
                except (shutil.Error, IOError) as e:
                    messages.append("Failed to copy data source: {0}".format(e))
            # restore original cursor
            QApplication.restoreOverrideCursor()

            if messages:
                raise Exception("Copying project files failed:\n{0}".format(os.linesep.join(messages)))

        def create_zip_project_file():
            dirpath = os.path.abspath(
                os.path.join(
                    self._publish_dir, os.pardir
                )
            )
            filename = os.path.basename(self._publish_dir)
            zip_out_file = os.path.join(dirpath, filename)

            shutil.make_archive(
                base_name=zip_out_file,
                format='zip',
                root_dir=dirpath,
                base_dir=filename
            )

        if self.plugin.run_in_gislab or self._publish_dir != self._publish_dir_default:
            # copy project and data files into destination folder
            try:
                copy_project_files() # link=self.plugin.run_in_gislab)
                copy_data_sources()  # link=self.plugin.run_in_gislab)
            except Exception as e:
                QMessageBox.critical(self.dialog, "Error", "{0}".format(e))
                return False

        if self.dialog.zip_published_project.isChecked():
            # create zip archive for published project (in parrent directory)
            try:
                create_zip_project_file()
            except OSError as e:
                QMessageBox.critical(self.dialog, "Error", "Creating zip file failed. {0}".format(e))
                return False

        return True


    def on_show(self):
        tree = self.dialog.tree_project_files
        create_formatted_tree(tree,
                              list(self.project_files())
        )
        tree.expandAll()

        # Data sources
        self._datasources = {}
        vector_data_file = opt_value(self.plugin.metadata, 'vector_layers.filename')
        if vector_data_file:
            self._datasources['Vector layers'] = [
                os.path.join(
                    os.path.dirname(
                        self.plugin.project.fileName()
                    ),
                    vector_data_file
                )
            ]

        def collect_layers_datasources(layer_node):
            for index in range(layer_node.rowCount()):
                collect_layers_datasources(
                    layer_node.child(index)
                )
            layer = layer_node.data(Qt.UserRole)
            if layer and layer_node.checkState() == Qt.Checked:
                layer_provider = layer.dataProvider()
                if isinstance(layer_provider, QgsVectorDataProvider):
                    storage_type = layer_provider.storageType()
                elif isinstance(layer_provider, QgsRasterDataProvider):
                    storage_type = 'Raster'
                else:
                    storage_type = 'Other'

                datasource_uri = QgsDataSourceUri( layer_provider.dataSourceUri() )
                datasource_db = datasource_uri.database()
                if datasource_db:
                    datasource_db = os.path.normpath(datasource_db)
                if storage_type not in self._datasources:
                    self._datasources[storage_type] = dict() if datasource_db else set()
                if datasource_db:
                    if datasource_db not in self._datasources[storage_type]:
                        self._datasources[storage_type][datasource_db] = []
                    if datasource_uri.schema():
                        table_name = '{0}.{1}'.format(datasource_uri.schema(), datasource_uri.table())
                    else:
                        table_name = datasource_uri.table()
                    table_item = [
                        "{0} ({1})".format(table_name, datasource_uri.geometryColumn())
                    ]
                    self._datasources[storage_type][datasource_db].append(table_item)
                    if datasource_uri.sql():
                        table_item.append(["SQL: {}".format(datasource_uri.sql())])
                else:
                    dsfile = layer_provider.dataSourceUri().split('|')[0].strip()
                    self._datasources[storage_type].add(os.path.normpath(dsfile))

        collect_layers_datasources(
            self.dialog.treeView.model().invisibleRootItem()
        )
        tree = self.dialog.tree_data_sources
        create_formatted_tree(tree, self._datasources)
        tree.expandAll()
