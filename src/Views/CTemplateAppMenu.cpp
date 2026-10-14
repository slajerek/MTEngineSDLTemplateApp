#include "CTemplateAppMenu.h"
#include "CViewTemplateAppMain.h"
#include "CTemplateAppI18n.h"
#include "CMTNativeMenuBar.h"
#include "CGuiMain.h"
#include "CLayoutManager.h"
#include "CI18nManager.h"
#include "CMTThemeRegistry.h"
#include "MT_Theme.h"
#include "MT_UiScale.h"
#include "SYS_DefaultConfig.h"
#include "SYS_Main.h"
#include "VID_Main.h"
#include <cstdio>
#include <cstring>
#include <string>

CTemplateAppMenu::CTemplateAppMenu(CViewTemplateAppMain *view)
: view(view)
{
	// Shortcuts live in the engine's shortcut system: only the native macOS bar
	// dispatches key equivalents, the ImGui and Win32 bars only display them.
	// The name is NOT translated: CSlrKeyboardShortcut hashes it into the
	// shortcut's identity, which a stored shortcut configuration refers to.
#if defined(MACOS)
	kbsQuitApplication = new CSlrKeyboardShortcut(MT_KEYBOARD_SHORTCUT_GLOBAL, "Quit application", 'q', false, false, true, false, this);
#else
	kbsQuitApplication = new CSlrKeyboardShortcut(MT_KEYBOARD_SHORTCUT_GLOBAL, "Quit application", MTKEY_F4, false, true, false, false, this);
#endif
	guiMain->AddKeyboardShortcut(kbsQuitApplication);
}

void CTemplateAppMenu::Setup(CMTNativeMenuBar *menuBar)
{
	bar = menuBar;
	if (bar)
		BuildMenus();
}

bool CTemplateAppMenu::ProcessKeyboardShortcut(u32 zone, u8 actionType, CSlrKeyboardShortcut *shortcut)
{
	if (shortcut == kbsQuitApplication)
	{
		SYS_Shutdown();
		return true;
	}
	return false;
}

void CTemplateAppMenu::BuildMenus()
{
	// File: Quit. The native macOS application menu already has Quit.
	const bool nativeMac =
#if defined(MACOS)
		bar->IsNative();
#else
		false;
#endif
	if (!nativeMac)
	{
		CMTMenu *file = bar->AddMenu(_T("menu.file"));
		file->AddItem(_T("menu.file.quit"), [this]{ kbsQuitApplication->Run(); }, kbsQuitApplication);
		topLevel.push_back(file);
	}

	workspaceMenu = bar->AddMenu(_T("menu.workspace"));
	topLevel.push_back(workspaceMenu);
	BuildWorkspaceMenu();

	// Settings holds ONLY submenus (ImGui backend shape rule).
	CMTMenu *settings = bar->AddMenu(_T("menu.settings"));
	topLevel.push_back(settings);

	CMTMenu *theme = settings->AddSubMenu(_T("menu.settings.theme"));
	{
		CMTThemeRegistry *registry = CMTThemeRegistry::Instance();
		std::vector<CMTThemeRegistry::Entry> entries;
		registry->EnumerateEntries(entries, /* devBuild */ true);
		for (const CMTThemeRegistry::Entry &e : entries)
		{
			if (e.isLegacyStyle)
			{
				const int style = e.legacyStyleType;
				CMTMenuItem *item = theme->AddItem(e.label, [this, style]{ Defer([style]{
					CMTThemeRegistry *r = CMTThemeRegistry::Instance();
					if (r->HasActiveTheme()) r->ClearActiveTheme();
					VID_SetDefaultImGuiStyle((ImGuiStyleType)style);
				}); });
				themeLegacyItems.push_back({style, item});
			}
			else
			{
				const std::string id = e.id;
				CMTMenuItem *item = theme->AddItem(e.label, [this, id]{ Defer([id]{
					CMTThemeRegistry *r = CMTThemeRegistry::Instance();
					// MT_GetUiScale(), not GetActiveGuiScale(): the registry only
					// remembers the scale of its last activation (1.0 before any).
					r->SetActiveTheme(id.c_str(), r->GetActiveMode(), MT_GetUiScale());
				}); });
				themeItems.push_back({id, item});
			}
		}
	}

	CMTMenu *renderer = settings->AddSubMenu(_T("menu.settings.renderer"));
	{
		const char *names[8];
		const int count = VID_GetAvailableRenderBackends(names, 8);
		for (int i = 0; i < count; i++)
		{
			const std::string name = names[i];
			CMTMenuItem *item = renderer->AddItem(VID_GetRenderBackendDisplayName(names[i]), [this, name]{ Defer([name]{
				VID_SetPreferredRenderBackend(name.c_str());
				// Takes effect on restart; say so, or the menu looks broken.
				guiMain->ShowMessageBox(_T("menu.settings.renderer.restart_title"),
				                        _T("menu.settings.renderer.restart_message"));
			}); });
			rendererItems.push_back({name, item});
		}
	}

	CMTMenu *scale = settings->AddSubMenu(_T("menu.settings.gui_scale"));
	for (int i = 0; i < MT_kGuiScaleStepCount; i++)
	{
		const float step = MT_kGuiScaleSteps[i];
		char label[16];
		snprintf(label, sizeof(label), "%d%%", (int)(step * 100.0f + 0.5f));
		CMTMenuItem *item = scale->AddItem(label, [this, step]{ Defer([step]{
			MT_SetUiScale(step);
			float applied = MT_GetUiScale();
			gApplicationDefaultConfig->SetFloat("ui.guiScale", &applied);
		}); });
		scaleItems.push_back({step, item});
	}

	CMTMenu *language = settings->AddSubMenu(_T("menu.settings.language"));
	for (const SI18nLocale &l : CI18nManager::Instance()->GetRegisteredLocales())
	{
		const std::string tag = l.tag;
		CMTMenuItem *item = language->AddItem(l.displayName.c_str(), [this, tag]{ Defer([this, tag]{
			CTemplateAppI18n::SetActive(tag);
			needsRebuild = true;   // labels are copied into the backend
		}); });
		localeItems.push_back({tag, item});
	}

	CMTMenu *help = bar->AddMenu(_T("menu.help"));
	topLevel.push_back(help);
	help->AddItem(_T("menu.help.about"),         [this]{ view->showAbout = true; });
	help->AddSeparator();
	help->AddItem(_T("menu.help.imgui_metrics"), [this]{ view->showImGuiMetrics = true; });
	help->AddItem(_T("menu.help.imgui_demo"),    [this]{ view->showImGuiDemo = true; });
	help->AddItem(_T("menu.help.imgui_about"),   [this]{ view->showImGuiAbout = true; });

	SyncCheckmarks();
}

void CTemplateAppMenu::BuildWorkspaceMenu()
{
	layoutItems.clear();
	for (CLayoutData *layout : guiMain->layoutManager->layouts)
	{
		CMTMenuItem *item = workspaceMenu->AddItem(layout->layoutName, [this, layout]{ Defer([layout]{
			guiMain->layoutManager->SetLayoutAsync(layout, true);
		}); }, layout->keyShortcut);
		layoutItems.push_back({layout, item});
	}
	workspaceMenu->AddSeparator();
	workspaceMenu->AddItem(_T("menu.workspace.new"), [this]{ view->openNewWorkspace = true; });
	workspaceMenu->AddItem(_T("menu.workspace.delete"), [this]{ Defer([]{
		CLayoutManager *lm = guiMain->layoutManager;
		if (lm->currentLayout == nullptr)
			return;   // nothing selected: Delete is a no-op, not a crash
		lm->RemoveAndDeleteLayout(lm->currentLayout);
		lm->StoreLayouts();
	}); });
	lastKnownLayouts = guiMain->layoutManager->layouts;
}

void CTemplateAppMenu::Rebuild()
{
	for (CMTMenu *m : topLevel)
		bar->RemoveMenu(m);
	topLevel.clear();
	workspaceMenu = nullptr;
	layoutItems.clear();
	themeLegacyItems.clear();
	themeItems.clear();
	rendererItems.clear();
	scaleItems.clear();
	localeItems.clear();
	BuildMenus();
}

void CTemplateAppMenu::SyncCheckmarks()
{
	for (auto &p : layoutItems)
		p.second->SetChecked(p.first == guiMain->layoutManager->currentLayout);

	CMTThemeRegistry *registry = CMTThemeRegistry::Instance();
	const char *activeTheme = registry->HasActiveTheme() ? registry->GetActiveThemeId() : nullptr;
	const int legacy = (int)VID_GetDefaultImGuiStyle();
	for (auto &p : themeLegacyItems) p.second->SetChecked(activeTheme == nullptr && p.first == legacy);
	for (auto &p : themeItems)       p.second->SetChecked(activeTheme != nullptr && p.first == activeTheme);

	const std::string effective = VID_GetEffectiveRenderBackendSelection();   // copy first: shared buffer
	for (auto &p : rendererItems) p.second->SetChecked(p.first == effective);

	const float current = MT_ThemeClampGuiScale(MT_GetUiScale());
	for (auto &p : scaleItems) p.second->SetChecked(MT_ThemeClampGuiScale(p.first) == current);

	const std::string &active = CI18nManager::Instance()->GetActiveLocale();
	for (auto &p : localeItems) p.second->SetChecked(p.first == active);
}

void CTemplateAppMenu::RunPendingAction()
{
	if (!pendingAction)
		return;
	std::function<void()> action = std::move(pendingAction);
	pendingAction = nullptr;
	action();
}

void CTemplateAppMenu::Sync()
{
	if (!bar)
	{
		// Native mode on headless macOS: no backend to rebuild, but the request
		// is still consumed, so callers see one contract in every mode.
		needsRebuild = false;
		return;
	}
	if (syncInProgress)
		return;
	// Mutating a Win32 HMENU can re-enter a render through SDL's resize filter;
	// never let that nested frame see a half-built menu.
	syncInProgress = true;

	if (needsRebuild)
	{
		needsRebuild = false;
		Rebuild();
	}
	else if (guiMain->layoutManager->layouts != lastKnownLayouts)
	{
		// The workspace menu holds only items, so RemoveAllItems() is complete here.
		workspaceMenu->RemoveAllItems();
		BuildWorkspaceMenu();
	}
	SyncCheckmarks();

	syncInProgress = false;
}

bool CTemplateAppMenu::KeyDown(u32 keyCode, bool isShift, bool isAlt, bool isControl, bool isSuper)
{
	if (!waitingForShortcut || pendingLayout == nullptr)
		return false;
	if (SYS_IsKeyCodeSpecial(keyCode))
		return false;

	if (pendingLayout->keyShortcut)
	{
		guiMain->RemoveKeyboardShortcut(pendingLayout->keyShortcut);
		delete pendingLayout->keyShortcut;
		pendingLayout->keyShortcut = nullptr;
	}

	CSlrKeyboardShortcut *existing = guiMain->keyboardShortcuts->FindShortcut(MT_KEYBOARD_SHORTCUT_GLOBAL, keyCode, isShift, isAlt, isControl, isSuper);
	if (existing)
	{
		char buf[256];
		snprintf(buf, sizeof(buf), _T("workspace.shortcut_taken"), existing->cstr, existing->name);
		guiMain->ShowMessageBox(_T("workspace.shortcut_taken_title"), buf);
		waitingForShortcut = false;
		return true;
	}

	// Workspace shortcuts are dispatched by CLayoutManager (a CSlrKeyboardShortcutCallback).
	pendingLayout->keyShortcut = new CSlrKeyboardShortcut(MT_KEYBOARD_SHORTCUT_GLOBAL, "", keyCode, isShift, isAlt, isControl, isSuper, guiMain->layoutManager);
	waitingForShortcut = false;
	return true;
}
