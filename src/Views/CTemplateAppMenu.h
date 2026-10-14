#ifndef _CTEMPLATEAPPMENU_H_
#define _CTEMPLATEAPPMENU_H_

#include "SYS_Defs.h"
#include "CSlrKeyboardShortcuts.h"
#include <functional>
#include <list>
#include <string>
#include <vector>

class CMTNativeMenuBar;
class CMTMenu;
class CMTMenuItem;
class CLayoutData;
class CViewTemplateAppMain;

// The app's ONE menu definition, written against CMTNativeMenuBar so the same
// code drives the ImGui and the native backends (see CLAUDE.md, Menu).
//
// Shape rules forced by CMTNativeMenuBarImGui: a menu holds items OR submenus
// (submenus render after all items), and RemoveAllItems() keeps submenus, so a
// rebuild removes and re-adds whole top-level menus.
class CTemplateAppMenu : public CSlrKeyboardShortcutCallback
{
public:
	explicit CTemplateAppMenu(CViewTemplateAppMain *view);

	void Setup(CMTNativeMenuBar *bar);
	void Sync();     // MT_PostRenderEndFrame() only -- never inside the ImGui frame
	bool KeyDown(u32 keyCode, bool isShift, bool isAlt, bool isControl, bool isSuper);
	virtual bool ProcessKeyboardShortcut(u32 zone, u8 actionType, CSlrKeyboardShortcut *shortcut) override;

	// Menu actions never do work themselves: under a native backend they run
	// outside the ImGui frame. They store the work here, and the main view runs
	// it at the start of its render pass (CLAUDE.md, Menu).
	void RunPendingAction();

	bool needsRebuild = false;
	CSlrKeyboardShortcut *kbsQuitApplication = nullptr;

	// New Workspace popup state (rendered by the main view)
	CLayoutData *pendingLayout = nullptr;
	bool waitingForShortcut = false;

private:
	void Rebuild();
	void BuildMenus();
	void BuildWorkspaceMenu();
	void SyncCheckmarks();

	void Defer(std::function<void()> action) { pendingAction = std::move(action); }

	CViewTemplateAppMain *view;
	CMTNativeMenuBar *bar = nullptr;
	bool syncInProgress = false;
	std::function<void()> pendingAction;

	std::vector<CMTMenu *> topLevel;
	CMTMenu *workspaceMenu = nullptr;
	std::list<CLayoutData *> lastKnownLayouts;
	std::vector<std::pair<CLayoutData *, CMTMenuItem *>> layoutItems;
	std::vector<std::pair<int, CMTMenuItem *>> themeLegacyItems;     // legacy style type
	std::vector<std::pair<std::string, CMTMenuItem *>> themeItems;   // registered theme id
	std::vector<std::pair<std::string, CMTMenuItem *>> rendererItems;
	std::vector<std::pair<float, CMTMenuItem *>> scaleItems;
	std::vector<std::pair<std::string, CMTMenuItem *>> localeItems;
};

#endif
