# -*- coding: utf-8 -*-
"""Spyder AI Chat Plugin (C) 2026 by Maciej Piecko"""

import logging

from qtpy.QtCore import QEvent, Qt, QObject, QTimer
from qtpy.QtWidgets import QApplication

from spyder.api.plugins import Plugins, SpyderDockablePlugin
from spyder.api.plugin_registration.decorators import (
    on_plugin_available, on_plugin_teardown,
)

from .confpage import AIChatConfigPage
from .widgets.chat_widget import AIChatWidget
from .fim.ghost_text import GhostTextManager

logger = logging.getLogger(__name__)


class _AltBackslashFilter(QObject):
    """App-level event filter for Alt+Backslash manual FIM trigger."""

    def __init__(self, plugin):
        super().__init__(QApplication.instance())
        self._plugin = plugin
        QApplication.instance().installEventFilter(self)

    def eventFilter(self, obj, event):
        if event.type() != QEvent.KeyPress:
            return False
        if not (event.modifiers() & Qt.AltModifier):
            return False
        if event.key() != Qt.Key_Backslash:
            return False
        try:
            self._plugin._fire_manual_fim()
        except Exception:
            pass
        return True

    def remove(self):
        app = QApplication.instance()
        if app:
            app.removeEventFilter(self)


class AIChatPlugin(SpyderDockablePlugin):

    NAME              = "ai_chat_plugin"
    WIDGET_CLASS      = AIChatWidget
    CONF_SECTION      = "ai_chat_plugin"
    CONF_WIDGET_CLASS = AIChatConfigPage
    REQUIRES          = [Plugins.Preferences]
    OPTIONAL          = [Plugins.Editor, Plugins.Completions, Plugins.IPythonConsole,
                         Plugins.Projects]
    TABIFY            = [Plugins.Help]

    # ── Plugin metadata ────────────────────────────────────────────────

    @staticmethod
    def get_name():
        return "AI 聊天"

    @staticmethod
    def get_description():
        return "通过 OpenAI 兼容 API 与 AI 聊天并获得内联 FIM 代码补全"

    @classmethod
    def get_icon(cls):
        try:
            import qtawesome as qta
            return qta.icon("mdi.chat-outline")
        except Exception:
            return cls.create_icon("editcopy")

    # ── Lifecycle ──────────────────────────────────────────────────────

    def on_initialize(self):
        widget = self.get_widget()
        widget.set_editor_cursor_fn(self._get_editor_cursor)
        widget.set_project_fns(self._get_project_root, self._get_editor_widget)
        widget.set_console_execute_fn(self._execute_in_console)
        widget.set_load_file_fn(self._load_file_in_editor)
        widget.set_reload_file_fn(self._reload_file_in_editor)

        # Ghost text: one GhostTextManager per editor (keyed by id(editor))
        self._ghost_managers     = {}
        # filename → editor, updated on every tab switch
        self._filename_to_editor = {}

        # App-level Alt+Backslash shortcut — independent of per-editor setup
        self._alt_bs_filter = _AltBackslashFilter(self)

    def on_close(self, cancellable=True):
        try:
            self._alt_bs_filter.remove()
        except Exception:
            pass
        for manager in self._ghost_managers.values():
            try:
                manager.cleanup()
            except Exception:
                pass
        self._ghost_managers.clear()
        self._filename_to_editor.clear()
        return True

    # ── Preferences ────────────────────────────────────────────────────

    @on_plugin_available(plugin=Plugins.Preferences)
    def on_preferences_available(self):
        self.get_plugin(Plugins.Preferences).register_plugin_preferences(self)

    @on_plugin_teardown(plugin=Plugins.Preferences)
    def on_preferences_teardown(self):
        self.get_plugin(Plugins.Preferences).deregister_plugin_preferences(self)

    # ── Editor plugin ──────────────────────────────────────────────────

    @on_plugin_available(plugin=Plugins.Editor)
    def on_editor_available(self):
        editor_plugin = self.get_plugin(Plugins.Editor)

        # sig_codeeditor_created fires for every new editor going forward
        editor_plugin.sig_codeeditor_created.connect(self._on_codeeditor_created)
        # sig_codeeditor_changed fires on every tab switch
        editor_plugin.sig_codeeditor_changed.connect(self._on_codeeditor_changed)

        # Register editors already open before our plugin loaded.
        # Uses editorstack.data directly — confirmed present in Spyder 6.1.3.
        self._register_existing_editors(editor_plugin)

        # Handle current editor immediately
        current = editor_plugin.get_current_editor()
        if current is not None:
            self._on_codeeditor_changed(current)

    @on_plugin_teardown(plugin=Plugins.Editor)
    def on_editor_teardown(self):
        editor_plugin = self.get_plugin(Plugins.Editor)
        try:
            editor_plugin.sig_codeeditor_created.disconnect(
                self._on_codeeditor_created)
        except Exception:
            pass
        try:
            editor_plugin.sig_codeeditor_changed.disconnect(
                self._on_codeeditor_changed)
        except Exception:
            pass

    def _on_codeeditor_created(self, codeeditor):
        """Install GhostTextManager on every new editor."""
        if codeeditor is None:
            return
        editor_id = id(codeeditor)
        if editor_id not in self._ghost_managers:
            manager = GhostTextManager(codeeditor)
            self._ghost_managers[editor_id] = manager
            logger.debug("GhostTextManager installed on editor %d", editor_id)

        # Context menu (idempotent guard inside)
        if not getattr(codeeditor, "_ai_chat_plugin_menu_installed", False):
            self._install_context_menu(codeeditor)
            codeeditor._ai_chat_plugin_menu_installed = True

    def _on_codeeditor_changed(self, codeeditor):
        """Track filename→editor on tab switch; install manager if missing."""
        if codeeditor is None:
            return
        # Ensure manager exists — catches startup file and any edge cases
        self._on_codeeditor_created(codeeditor)
        try:
            editor_plugin = self.get_plugin(Plugins.Editor)
            filename = editor_plugin.get_current_filename() or ""
            if filename:
                self._filename_to_editor[filename] = codeeditor
                # Seed FIM provider with current text if it missed DID_OPEN
                self._seed_provider_text(filename, codeeditor)
        except Exception:
            pass

    def _register_existing_editors(self, editor_plugin):
        """Install managers on editors open before our plugin loaded.

        Walks editorstack.data directly (confirmed in editorstack.py 6.1.3):
          editorstack.data is a list of FileInfo with .editor and .filename.
        """
        seen = set()
        try:
            widget = editor_plugin.get_widget()
            for editorstack in self._iter_editorstacks(widget):
                if not hasattr(editorstack, 'data'):
                    continue
                for finfo in editorstack.data:
                    editor   = getattr(finfo, 'editor',   None)
                    filename = getattr(finfo, 'filename',  '')
                    if editor is None or id(editor) in seen:
                        continue
                    seen.add(id(editor))
                    self._on_codeeditor_created(editor)
                    if filename:
                        self._filename_to_editor[filename] = editor
                        self._seed_provider_text(filename, editor)
        except Exception as e:
            logger.debug("_register_existing_editors failed: %s", e)

    def _iter_editorstacks(self, widget):
        """Recursively find all EditorStack widgets."""
        from qtpy.QtWidgets import QWidget
        results = []
        try:
            if type(widget).__name__ == 'EditorStack':
                results.append(widget)
            for child in widget.children():
                if isinstance(child, QWidget):
                    results.extend(self._iter_editorstacks(child))
        except Exception:
            pass
        return results

    def _seed_provider_text(self, filename, editor):
        """Push editor text into FIM provider cache ONLY if completely absent.

        This handles the startup file whose DID_OPEN fired before our provider
        was registered. Once send_notification(DID_CHANGE) fires it will
        overwrite this with live text — so we only seed when truly missing.
        We do NOT guard with 'if already present: return' because that would
        permanently block DID_CHANGE updates from overwriting a stale seed.
        Instead we check _document_texts is empty/missing for this file.
        """
        try:
            from .fim.provider import _INSTANCE as fim_provider
            if fim_provider is None:
                return
            # Only seed if there is genuinely nothing tracked yet
            if fim_provider._document_texts.get(filename):
                return
            text = editor.toPlainText()
            if text:
                fim_provider._document_texts[filename] = text
                logger.debug("Seeded %d chars for %s (will be overwritten by DID_CHANGE)",
                             len(text), filename)
        except Exception as e:
            logger.debug("_seed_provider_text failed: %s", e)

    # ── Context menu ───────────────────────────────────────────────────

    def _install_context_menu(self, codeeditor):
        """Inject an 'AI Chat' submenu into the editor right-click menu.

        Spyder 6.1.4 changed the context menu from a plain ``codeeditor.menu``
        attribute to menus registered under string IDs and fetched via
        ``codeeditor.get_menu('context_menu')``.  We try the new API first and
        fall back to the old attribute so the plugin works on both versions.

        SpyderMenu.render() is connected to aboutToShow with a direct connection
        in SpyderMenu.__init__, so it fires *before* our handler — clearing and
        rebuilding the menu — and our submenu is appended on top of the result.
        A fresh submenu is built every call; any stale copy is removed first.
        """
        try:
            from qtpy.QtWidgets import QAction, QMenu, QShortcut
            from qtpy.QtGui import QKeySequence
            from qtpy.QtCore import Qt
            plugin_ref = self

            def _inject(menu):
                """Remove stale AI Chat entry then append a fresh one.

                Checks project-context state on every call so the enabled/
                disabled state of 'Add file to context' is always current,
                regardless of which chat window is active.
                """
                if menu is None:
                    return
                for act in list(menu.actions()):
                    m = act.menu()
                    if m and m.title() == "AI Chat":
                        menu.removeAction(act)
                        break
                try:
                    ed = plugin_ref.get_plugin(Plugins.Editor).get_current_editor()
                    has_sel = bool(ed and ed.get_selected_text())
                except Exception:
                    has_sel = False
                # Disable "Add file" when project context is ON — individual
                # file attachments are blocked to avoid duplicating context.
                try:
                    proj_on = plugin_ref.get_widget().is_project_context_enabled()
                except Exception:
                    proj_on = False
                sub = QMenu("AI Chat", menu)
                file_act = QAction("➕ Add file to context", sub)
                file_act.setShortcut(QKeySequence("Ctrl+Shift+A"))
                file_act.setEnabled(not proj_on)
                file_act.triggered.connect(plugin_ref._on_add_current_file)
                sel_act = QAction("➕ Add selection to context", sub)
                sel_act.setShortcut(QKeySequence("Ctrl+Shift+Q"))
                sel_act.setEnabled(has_sel)
                sel_act.triggered.connect(plugin_ref._on_add_selection)
                sub.addAction(file_act)
                sub.addAction(sel_act)
                menu.addSeparator()
                menu.addMenu(sub)

            connected = False

            # ── Spyder 6.1.4+: menus registered under string IDs ────────────
            if hasattr(codeeditor, "get_menu"):
                for menu_id in ("context_menu", "read_only_menu"):
                    try:
                        m = codeeditor.get_menu(menu_id)
                        if m is not None:
                            m.aboutToShow.connect(lambda checked=False, _m=m: _inject(_m))
                            connected = True
                    except Exception:
                        pass

            # ── Spyder ≤6.1.3 fallback: plain .menu attribute ───────────────
            if not connected:
                old_menu = getattr(codeeditor, "menu", None)
                if old_menu is not None:
                    old_menu.aboutToShow.connect(lambda checked=False, _m=old_menu: _inject(_m))
                    connected = True

            if not connected:
                logger.warning(
                    "AI Chat: could not find editor context menu "
                    "(neither get_menu() IDs nor .menu attribute found)")

            # ── Per-editor keyboard shortcuts ────────────────────────────────
            # Qt.WidgetWithChildrenShortcut: fires only when this editor (or a
            # child widget of it) has keyboard focus, so the shortcuts don't
            # interfere with the rest of Spyder.  The QShortcut is parented to
            # codeeditor and is destroyed automatically when the editor closes.
            file_sc = QShortcut(QKeySequence("Ctrl+Shift+A"), codeeditor)
            file_sc.setContext(Qt.WidgetWithChildrenShortcut)
            file_sc.activated.connect(plugin_ref._on_add_current_file)

            sel_sc = QShortcut(QKeySequence("Ctrl+Shift+Q"), codeeditor)
            sel_sc.setContext(Qt.WidgetWithChildrenShortcut)
            sel_sc.activated.connect(plugin_ref._on_add_selection)

        except Exception as e:
            logger.warning("AI Chat: context menu install failed: %s", e)

    # ── Projects plugin ───────────────────────────────────────────────

    @on_plugin_available(plugin=Plugins.Projects)
    def on_projects_available(self):
        projects = self.get_plugin(Plugins.Projects)
        try:
            projects.sig_project_loaded.connect(self._on_project_loaded)
            projects.sig_project_closed.connect(self._on_project_closed)
        except Exception as e:
            logger.debug("Projects signals connect failed: %s", e)
        # Pick up a project that was already open before this plugin became available.
        # sig_project_loaded only fires for newly loaded projects, so without this
        # the plugin would never learn the initial project root on startup.
        try:
            path = projects.get_active_project_path()
            if path:
                self._on_project_loaded(path)
        except Exception as e:
            logger.debug("Initial project root detection failed: %s", e)
        self._install_project_explorer_menu(projects)

    @on_plugin_teardown(plugin=Plugins.Projects)
    def on_projects_teardown(self):
        try:
            projects = self.get_plugin(Plugins.Projects)
            projects.sig_project_loaded.disconnect(self._on_project_loaded)
            projects.sig_project_closed.disconnect(self._on_project_closed)
        except Exception:
            pass

    def _install_project_explorer_menu(self, projects_plugin):
        """Inject an 'AI Chat' submenu into the Project Explorer context menu.

        Finds the ProjectExplorerTreeWidget, connects to its context menu's
        aboutToShow signal, and injects a fresh submenu on every right-click.
        Single file selected → 'Add file to context'.
        Multiple files selected → 'Add N files to context'.
        Only regular files are offered (directories are silently skipped).
        """
        import os as _os
        try:
            from qtpy.QtWidgets import QAction, QMenu
            plugin_ref = self

            tree = self._find_widget_by_classname(
                projects_plugin.get_widget(), "ProjectExplorerTreeWidget")
            if tree is None:
                logger.warning(
                    "AI Chat: ProjectExplorerTreeWidget not found — "
                    "project pane context menu not installed")
                return

            # SpyderMenu stored as .context_menu on DirView
            ctx_menu = getattr(tree, "context_menu", None)
            if ctx_menu is None:
                try:
                    ctx_menu = tree.get_menu("context")
                except Exception:
                    pass
            if ctx_menu is None:
                logger.warning(
                    "AI Chat: project explorer context menu not found")
                return

            def _inject_proj(menu):
                if menu is None:
                    return
                # Remove stale entry
                for act in list(menu.actions()):
                    m = act.menu()
                    if m and m.title() == "AI Chat":
                        menu.removeAction(act)
                        break
                # Collect selected files (skip directories)
                try:
                    fnames = [f for f in (tree.get_selected_filenames() or [])
                              if f and _os.path.isfile(f)]
                except Exception:
                    fnames = []
                if not fnames:
                    return
                # Disable when project context is ON (same rule as editor menu)
                try:
                    proj_on = plugin_ref.get_widget().is_project_context_enabled()
                except Exception:
                    proj_on = False

                sub = QMenu("AI Chat", menu)
                n = len(fnames)
                label = ("➕ Add file to context"
                         if n == 1 else f"➕ Add {n} files to context")
                add_act = QAction(label, sub)
                add_act.setEnabled(not proj_on)

                def _do_add(checked=False, _files=fnames):
                    for fpath in _files:
                        try:
                            name = _os.path.normpath(_os.path.abspath(fpath))
                            with open(fpath, "r",
                                      encoding="utf-8", errors="replace") as fh:
                                content = fh.read()
                            plugin_ref.get_widget().add_file_context_content(
                                name, content)
                        except Exception as exc:
                            logger.debug(
                                "AI Chat: add project file failed: %s", exc)

                add_act.triggered.connect(_do_add)
                sub.addAction(add_act)
                menu.addSeparator()
                menu.addMenu(sub)

            ctx_menu.aboutToShow.connect(
                lambda checked=False, _m=ctx_menu: _inject_proj(_m))

        except Exception as e:
            logger.warning(
                "AI Chat: project explorer menu install failed: %s", e)

    def _find_widget_by_classname(self, widget, classname):
        """Recursively find the first child widget with the given class name."""
        from qtpy.QtWidgets import QWidget
        if type(widget).__name__ == classname:
            return widget
        for child in widget.children():
            if isinstance(child, QWidget):
                result = self._find_widget_by_classname(child, classname)
                if result is not None:
                    return result
        return None

    def _on_project_loaded(self, path):
        try:
            self.get_widget().on_project_loaded(path)
        except Exception as e:
            logger.debug("on_project_loaded failed: %s", e)

    def _on_project_closed(self):
        try:
            self.get_widget().on_project_closed()
        except Exception as e:
            logger.debug("on_project_closed failed: %s", e)

    def _get_project_root(self):
        """Return active project root path or None."""
        try:
            projects = self.get_plugin(Plugins.Projects, error=False)
            if projects is None:
                return None
            return projects.get_active_project_path()
        except Exception:
            return None

    def _get_editor_widget(self):
        """Return the Editor plugin's main widget (for buffer access)."""
        try:
            editor_plugin = self.get_plugin(Plugins.Editor, error=False)
            if editor_plugin is None:
                return None
            return editor_plugin.get_widget()
        except Exception:
            return None

    # ── IPython console plugin ─────────────────────────────────────────

    @on_plugin_available(plugin=Plugins.IPythonConsole)
    def on_ipython_console_available(self):
        ipyconsole = self.get_plugin(Plugins.IPythonConsole)
        # sig_shellwidget_created fires for new kernels (first connect only)
        ipyconsole.sig_shellwidget_created.connect(self._on_shellwidget_created)
        # sig_shellwidget_changed fires on console tab switches — lets us patch
        # any console the user switches to (idempotency guard prevents re-patching)
        ipyconsole.sig_shellwidget_changed.connect(self._on_shellwidget_created)
        # Patch all consoles that already exist at plugin-load time by iterating
        # the main widget's clients list (each client.shellwidget is a ShellWidget)
        try:
            main_widget = ipyconsole.get_widget()
            for client in getattr(main_widget, 'clients', []):
                sw = getattr(client, 'shellwidget', None)
                if sw is not None:
                    self._on_shellwidget_created(sw)
        except Exception as e:
            logger.debug("IPython console existing clients patch failed: %s", e)

    @on_plugin_teardown(plugin=Plugins.IPythonConsole)
    def on_ipython_console_teardown(self):
        try:
            ipyconsole = self.get_plugin(Plugins.IPythonConsole)
            ipyconsole.sig_shellwidget_created.disconnect(
                self._on_shellwidget_created)
            ipyconsole.sig_shellwidget_changed.disconnect(
                self._on_shellwidget_created)
        except Exception:
            pass

    def _on_shellwidget_created(self, shellwidget):
        """Hook into the IPython console context menu via aboutToShow.

        SpyderMenu.render() is connected to aboutToShow first (in SpyderMenu
        __init__) and calls self.clear() + rebuilds Spyder-tracked actions.
        We connect after render, so our handler fires second — after the menu
        is fully rebuilt — and appends the AI Chat submenu at the bottom.
        """
        if shellwidget is None:
            return
        if getattr(shellwidget, '_ai_chat_plugin_menu_installed', False):
            return
        shellwidget._ai_chat_plugin_menu_installed = True

        from spyder.plugins.ipythonconsole.api import IPythonConsoleWidgetMenus
        from qtpy.QtWidgets import QAction, QMenu

        try:
            context_menu = shellwidget.get_menu(
                IPythonConsoleWidgetMenus.ClientContextMenu)
        except Exception as e:
            logger.debug("Could not get console context menu: %s", e)
            return

        plugin_ref = self
        sw_ref = shellwidget

        def _on_console_menu_about_to_show():
            # render() already ran (connected first) and called clear() +
            # re-added all Spyder-tracked items.  We now append our submenu.
            # Remove any stale AI Chat entry left if render() didn't clear().
            for act in list(context_menu.actions()):
                m = act.menu()
                if m and m.title() == "AI Chat":
                    context_menu.removeAction(act)
                    break

            submenu = QMenu("AI Chat", context_menu)

            add_all_act = QAction("➕ Add console content to context", submenu)
            add_all_act.triggered.connect(plugin_ref._on_add_console_content)
            submenu.addAction(add_all_act)

            sel = sw_ref._control.textCursor().selection().toPlainText()
            add_sel_act = QAction("➕ Add selection to context", submenu)
            add_sel_act.setEnabled(bool(sel.strip()))
            add_sel_act.triggered.connect(plugin_ref._on_add_console_selection)
            submenu.addAction(add_sel_act)

            context_menu.addSeparator()
            context_menu.addMenu(submenu)

        context_menu.aboutToShow.connect(_on_console_menu_about_to_show)

    def _execute_in_console(self, code, on_output=None):
        """Execute code in the active IPython console (used by agentic actions).

        If *on_output* is provided, the plugin attempts to capture the console
        output that appears after execution by connecting to sig_prompt_ready.
        When the kernel finishes and the next prompt appears, on_output(text) is
        called with the captured text (ANSI stripped).  Returns True if async
        capture was successfully set up, False otherwise.
        """
        import re as _re
        async_capture = False
        try:
            ipyconsole = self.get_plugin(Plugins.IPythonConsole, error=False)
            if ipyconsole is None:
                return False
            sw = ipyconsole.get_current_shellwidget()
            if sw is None:
                return False

            if on_output is not None:
                # Snapshot length of existing console text so we know where
                # the new output starts after execution.
                _before = len(sw._control.toPlainText())

                def _on_prompt_ready():
                    try:
                        sw.sig_prompt_ready.disconnect(_on_prompt_ready)
                    except Exception:
                        pass
                    raw   = sw._control.toPlainText()[_before:]
                    clean = _re.sub(
                        r'\x1b\[[0-9;]*[mABCDEFGHJKLMSTfsu]', '', raw).strip()
                    on_output(clean)

                try:
                    sw.sig_prompt_ready.connect(_on_prompt_ready)
                    async_capture = True
                except Exception:
                    pass   # signal not available — fall through without capture

            sw.execute(code)
        except Exception as e:
            logger.debug("_execute_in_console failed: %s", e)
        return async_capture

    def _load_file_in_editor(self, path):
        """Open a file in the Spyder editor (used after agentic file creation)."""
        try:
            editor_plugin = self.get_plugin(Plugins.Editor, error=False)
            if editor_plugin is None:
                return
            editor_plugin.load(path)
        except Exception as e:
            logger.debug("_load_file_in_editor failed: %s", e)

    def _reload_file_in_editor(self, path):
        """Reload an already-open file from disk (used after agentic patch application).

        Only reloads if the file is currently open in an editor tab; does not
        open files that are not already loaded.
        """
        import os as _os
        try:
            editor_plugin = self.get_plugin(Plugins.Editor, error=False)
            if editor_plugin is None:
                return
            norm = _os.path.normpath(_os.path.abspath(path))
            editorstack = editor_plugin.get_current_editorstack()
            if editorstack is None:
                return
            filenames = editorstack.get_filenames()
            for idx, fname in enumerate(filenames):
                if _os.path.normpath(_os.path.abspath(fname)) == norm:
                    editorstack.reload(idx)
                    return
        except Exception as e:
            logger.debug("_reload_file_in_editor failed: %s", e)

    def _on_add_console_content(self):
        """Add full IPython console text as a context attachment."""
        try:
            import re
            sw = self.get_plugin(Plugins.IPythonConsole).get_current_shellwidget()
            if sw is None:
                return
            text = sw._control.toPlainText()
            # Strip ANSI escape codes
            text = re.sub(r'\x1b\[[0-9;]*[mABCDEFGHJKLMSTfsu]', '', text)
            if not text.strip():
                return
            self.get_widget().add_file_context_content(
                "IPython Console", text, source="console")
        except Exception as e:
            logger.debug("Add console content failed: %s", e)

    def _on_add_console_selection(self):
        """Add selected IPython console text as a context attachment."""
        try:
            import re
            sw = self.get_plugin(Plugins.IPythonConsole).get_current_shellwidget()
            if sw is None:
                return
            sel = sw._control.textCursor().selection().toPlainText()
            sel = re.sub(r'\x1b\[[0-9;]*[mABCDEFGHJKLMSTfsu]', '', sel)
            if not sel.strip():
                return
            sel_id = self.get_widget().next_selection_id("IPython Console")
            name = f"Console selection {sel_id}"
            self.get_widget().add_file_context_content(name, sel, source="console")
        except Exception as e:
            logger.debug("Add console selection failed: %s", e)

    # ── Completions plugin ─────────────────────────────────────────────

    @on_plugin_available(plugin=Plugins.Completions)
    def on_completions_available(self):
        self._connect_ghost_text_retries = 0
        self._try_connect_ghost_text()
        # Retry until language_status is populated, then register our provider.
        self._fix_language_retries = 0
        self._schedule_fix_language_status()
        # Also hook the signal that fires each time a language becomes ready
        try:
            completions_plugin = self.get_plugin(Plugins.Completions)
            completions_plugin.sig_language_completions_available.connect(
                self._on_language_completions_available)
        except Exception as e:
            logger.debug("sig_language_completions_available connect failed: %s", e)

    def _on_language_completions_available(self, completion_capabilities, language):
        """Called when LSP finishes starting for a language.
        Re-run start_completion_services_for_language so our provider
        gets registered in language_status for this language.
        """
        try:
            completions_plugin = self.get_plugin(Plugins.Completions)
            completions_plugin.start_completion_services_for_language(language)
            logger.debug("Language available: %s -> %s", language,
                         completions_plugin.language_status.get(language))
        except Exception as e:
            logger.debug("_on_language_completions_available failed: %s", e)

    def _schedule_fix_language_status(self):
        QTimer.singleShot(500, self._fix_language_status)

    def _fix_language_status(self):
        """Retroactively register ai_fim_provider for all currently open languages.
        Retries every 500ms until language_status is populated (up to 30s).
        """
        try:
            completions_plugin = self.get_plugin(Plugins.Completions)
            lang_status = completions_plugin.language_status

            if not lang_status:
                self._fix_language_retries += 1
                if self._fix_language_retries < 60:
                    self._schedule_fix_language_status()
                else:
                    logger.warning("_fix_language_status: giving up after 60 retries")
                return

            for language in list(lang_status.keys()):
                completions_plugin.start_completion_services_for_language(language)
                logger.debug("Re-registered ai_fim_provider for language: %s", language)

        except Exception as e:
            logger.debug("_fix_language_status failed: %s", e)

    def _get_editor_text(self, filename):
        """Return live editor text for filename — used by FIM provider."""
        editor = self._filename_to_editor.get(filename)
        if editor is not None:
            return editor.toPlainText()
        return ""

    def _get_editor_cursor_offset(self, filename):
        """Return live cursor (line, col) for filename — used by FIM provider.
        Returns 0-based (blockNumber, columnNumber) so the provider can compute
        the correct byte offset in its document text regardless of line endings.
        """
        editor = self._filename_to_editor.get(filename)
        if editor is not None:
            cursor = editor.textCursor()
            return (cursor.blockNumber(), cursor.columnNumber())
        return None

    def _try_connect_ghost_text(self):
        """Connect to ai_fim_provider with retry (loads asynchronously)."""
        try:
            completions_plugin = self.get_plugin(Plugins.Completions)
            # Confirmed structure in completion/plugin.py 6.1.3:
            # self.providers[name] = {'instance': ..., 'status': ...}
            provider_info = completions_plugin.providers.get("ai_fim_provider")
            if provider_info and isinstance(provider_info, dict):
                provider = provider_info.get("instance")
                if provider is not None:
                    provider.sig_ghost_text_ready.connect(
                        self._on_ghost_text_ready)
                    # Give provider a direct line to live editor text and cursor
                    provider._get_editor_text_fn = self._get_editor_text
                    provider._get_cursor_offset_fn = self._get_editor_cursor_offset
                    logger.info("Ghost text signal connected to ai_fim_provider")
                    return
            self._connect_ghost_text_retries += 1
            if self._connect_ghost_text_retries <= 10:
                logger.debug("ai_fim_provider not ready, retry %d/10",
                             self._connect_ghost_text_retries)
                QTimer.singleShot(500, self._try_connect_ghost_text)
            else:
                logger.warning("ai_fim_provider not found after 10 retries")
        except Exception as e:
            logger.warning("Failed to wire ghost text signal: %s", e)

    @on_plugin_teardown(plugin=Plugins.Completions)
    def on_completions_teardown(self):
        try:
            completions_plugin = self.get_plugin(Plugins.Completions)
            provider_info = completions_plugin.providers.get("ai_fim_provider")
            if provider_info and isinstance(provider_info, dict):
                provider = provider_info.get("instance")
                if provider is not None:
                    provider.sig_ghost_text_ready.disconnect(
                        self._on_ghost_text_ready)
        except Exception:
            pass

    # ── Ghost text routing ─────────────────────────────────────────────

    def _on_ghost_text_ready(self, filename, text, target):
        editor = self._filename_to_editor.get(filename)
        if editor is None:
            logger.debug("No editor for %s, skipping ghost text", filename)
            return
        manager = self._ghost_managers.get(id(editor))
        if manager is None:
            logger.debug("No ghost manager for editor %d", id(editor))
            return
        shown = manager.show_suggestion(text, target=target)
        if not shown:
            logger.debug("Ghost text suppressed for %s (target moved)", filename)

    # ── Manual FIM trigger (Alt+Backslash) ────────────────────────────

    def _fire_manual_fim(self):
        """Fire immediate FIM completion bypassing trigger_mode/debounce."""
        try:
            from .fim.provider import _INSTANCE as fim_provider
            if fim_provider is None:
                return
            editor_plugin = self.get_plugin(Plugins.Editor)
            editor   = editor_plugin.get_current_editor()
            filename = editor_plugin.get_current_filename() or ""
            if editor is None:
                return
            # Seed text first in case this is the startup file
            if filename:
                self._seed_provider_text(filename, editor)
            cursor = editor.textCursor()
            fim_provider._handle_completion(
                {"file":   filename,
                 "offset": cursor.position(),
                 "line":   cursor.blockNumber(),
                 "column": cursor.columnNumber()},
                req_id=None,
                force=True,
            )
        except Exception as e:
            logger.debug("Manual FIM failed: %s", e)

    # ── Editor context helpers ─────────────────────────────────────────

    def _get_editor_cursor(self):
        """Return (QTextCursor, editor) for the current editor.

        Used by AIChatPanel._insert_to_editor to insert code at the cursor.
        Returns (None, diagnostic_str) when no editor is available.
        """
        try:
            editor_plugin = self.get_plugin(Plugins.Editor)
            editor = editor_plugin.get_current_editor()
            if editor is None:
                return None, "No editor open"
            return editor.textCursor(), editor
        except Exception as e:
            return None, str(e)

    def _get_current_editor_and_filename(self):
        try:
            import os
            editor_plugin = self.get_plugin(Plugins.Editor)
            editor   = editor_plugin.get_current_editor()
            filename = editor_plugin.get_current_filename() or ""
            name     = os.path.basename(filename) if filename else "unsaved"
            return editor, name
        except Exception:
            return None, None

    # ── Context menu actions ───────────────────────────────────────────

    def _on_add_current_file(self):
        try:
            import os
            editor_plugin = self.get_plugin(Plugins.Editor)
            filename = editor_plugin.get_current_filename() or ""
            editor   = editor_plugin.get_current_editor()
            text     = editor.toPlainText() if editor else ""
            if text:
                name = os.path.normpath(os.path.abspath(filename)) if filename else "unsaved"
                self.get_widget().add_file_context_content(name, text)
        except Exception as e:
            logger.debug("Add file failed: %s", e)

    def _on_add_selection(self):
        try:
            import os
            editor_plugin = self.get_plugin(Plugins.Editor)
            filename = editor_plugin.get_current_filename() or ""
            editor   = editor_plugin.get_current_editor()
            sel      = editor.get_selected_text() if editor else ""
            if sel:
                base   = os.path.normpath(os.path.abspath(filename)) if filename else "unsaved"
                sel_id = self.get_widget().next_selection_id(filename)
                name   = f"{base} selection {sel_id}"
                self.get_widget().add_file_context_content(
                    name, sel, source="selection")
        except Exception as e:
            logger.debug("Add selection failed: %s", e)

    # ── Misc ───────────────────────────────────────────────────────────

    def register(self):
        pass
