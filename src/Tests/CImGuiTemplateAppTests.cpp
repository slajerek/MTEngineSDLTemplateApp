#if MT_ENABLE_IMGUI_TEST_ENGINE
#include "imgui.h"
#include "imgui_te_engine.h"
#include "imgui_te_context.h"
#include "CGuiMain.h"
#include "CI18nManager.h"
#include "CMTNativeMenuBar.h"
#include "CViewTemplateAppMain.h"
#include "CTemplateAppMenu.h"
#include "CTemplateAppI18n.h"
#include "CLayoutManager.h"
#include "SYS_DefaultConfig.h"
#include "CConfigStorageHjson.h"
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <string>

// SDL3/SDL.h (pulled in via CGuiMain.h) drags in <windows.h> on Windows,
// which redefines the legacy Win16 macro Yield() -- undoing
// imgui_te_context.h's own #undef and turning every ctx->Yield() below into a
// syntax error. Same guard as imgui_te_context.h.
#ifdef Yield
#undef Yield
#endif

// Only the ImGui backend draws a menu ImGui can see; under a native bar the
// menu tests verify through the view's flags instead.
static bool ImGuiMenuBar()
{
	return guiMain->nativeMenuBar != nullptr && !guiMain->nativeMenuBar->IsNative();
}

// Menu-bar entries are not direct children of the menu-bar window: ImGui
// submits them inside its "##MenuBar" child.
// ItemInfo(<label>) relative to "##MainMenuBar" therefore finds nothing; this
// path does. MenuClick() builds the same path internally, so it may still be
// called relative to SetRef("##MainMenuBar").
static const char *const kMenuBarPath = "//##MainMenuBar/##MenuBar";

// Top-level menu ("File", "Help", ...). Submitted every frame, so no menu has
// to be open and nothing is activated.
static bool TopLevelMenuExists(ImGuiTestContext *ctx, const char *name)
{
	char path[256];
	snprintf(path, sizeof(path), "%s/%s", kMenuBarPath, name);
	return ctx->ItemInfo(path, ImGuiTestOpFlags_NoError).ID != 0;
}

// A scratch locale whose top-level labels differ from English. "zy" is a tag
// no app ships, and not CTestI18nLocales' "zz": LoadStrings() merges into a
// same-tag table, and that test expects zz's "menu.help" to fall back to en.
// It stays registered for the rest of the (test) process: the engine has no
// UnregisterLocale.
static const char *const kScratchTag  = "zy";
static const char *const kScratchName = "Scratch Menu";
static const char *const kScratchHelp = "ZY-Help";

static bool RegisterScratchLocale()
{
	namespace fs = std::filesystem;
	std::error_code ec;
	const fs::path dir = fs::temp_directory_path() / "templateapp-menu-i18n-test";
	fs::remove_all(dir, ec);
	fs::create_directories(dir, ec);
	{
		std::ofstream f(dir / "zy.json");
		f << R"({"meta":{"locale":"zy","displayName":"Scratch Menu","fallbacks":["en"],"version":1},)"
		     R"("strings":{"menu.file":"ZY-File","menu.workspace":"ZY-Workspace",)"
		     R"("menu.settings":"ZY-Settings","menu.help":"ZY-Help"}})";
	}
	const int loaded = CTemplateAppI18n::LoadLocalesFromDir(dir.string() + "/");
	fs::remove_all(dir, ec);
	return loaded == 1;
}

static CViewTemplateAppMain *MainView()
{
	return dynamic_cast<CViewTemplateAppMain *>(guiMain->currentView);
}

void RegisterTemplateAppTests(ImGuiTestEngine *engine)
{
	ImGuiTest *t = IM_REGISTER_TEST(engine, "ui", "menu_top_level");
	t->TestFunc = [](ImGuiTestContext *ctx)
	{
		if (!ImGuiMenuBar()) { ctx->LogInfo("native or no menu bar: skipped by design"); return; }
		IM_CHECK(TopLevelMenuExists(ctx, _T("menu.file")));   // the ImGui bar has File everywhere
		IM_CHECK(TopLevelMenuExists(ctx, _T("menu.workspace")));
		IM_CHECK(TopLevelMenuExists(ctx, _T("menu.settings")));
		IM_CHECK(TopLevelMenuExists(ctx, _T("menu.help")));
	};

	t = IM_REGISTER_TEST(engine, "ui", "help_about_opens_and_closes");
	t->TestFunc = [](ImGuiTestContext *ctx)
	{
		CViewTemplateAppMain *view = MainView();
		IM_CHECK(view != nullptr);
		if (ImGuiMenuBar())
		{
			ctx->SetRef("##MainMenuBar");
			ctx->MenuClick((std::string(_T("menu.help")) + "/" + _T("menu.help.about")).c_str());
		}
		else
		{
			view->showAbout = true;   // a native menu item's action sets exactly this
		}
		for (int i = 0; i < 10 && ctx->WindowInfo("//###TemplateAppAbout", ImGuiTestOpFlags_NoError).ID == 0; i++)
			ctx->Yield();
		IM_CHECK(ctx->WindowInfo("//###TemplateAppAbout", ImGuiTestOpFlags_NoError).ID != 0);
		view->showAbout = false;
		ctx->Yield(); ctx->Yield();
		IM_CHECK(ctx->WindowInfo("//###TemplateAppAbout", ImGuiTestOpFlags_NoError).Window == nullptr
		      || !ctx->WindowInfo("//###TemplateAppAbout", ImGuiTestOpFlags_NoError).Window->Active);
	};

	t = IM_REGISTER_TEST(engine, "ui", "language_switch_rebuilds_menu");
	t->TestFunc = [](ImGuiTestContext *ctx)
	{
		CViewTemplateAppMain *view = MainView();
		IM_CHECK(view != nullptr && view->menu != nullptr);
		CI18nManager *mgr = CI18nManager::Instance();

		// Everything changed here is restored exactly: the active locale and the
		// saved "locale" setting, including its absence.
		const std::string before = mgr->GetActiveLocale();
		const bool hadSaved = gApplicationDefaultConfig->E_x_i_s_t_s("locale");
		std::string saved;
		gApplicationDefaultConfig->GetStdString("locale", &saved, "");
		const std::string labelBefore = _T("menu.help");

		IM_CHECK(RegisterScratchLocale());
		// The Language submenu lists the locales known at the last build.
		view->menu->needsRebuild = true;
		ctx->Yield(3);
		IM_CHECK(view->menu->needsRebuild == false);   // Sync() consumed it without crashing

		// Switch the way a user does: Settings > Language > <scratch>.
		if (ImGuiMenuBar())
		{
			ctx->SetRef("##MainMenuBar");
			ctx->MenuClick((std::string(_T("menu.settings")) + "/" + _T("menu.settings.language") + "/" + kScratchName).c_str());
		}
		else
		{
			// What the Language item's deferred action does.
			CTemplateAppI18n::SetActive(kScratchTag);
			view->menu->needsRebuild = true;
		}
		ctx->Yield(5);
		const bool switched = mgr->GetActiveLocale() == kScratchTag;
		const bool rebuilt = view->menu->needsRebuild == false;
		const bool translatedShown = !ImGuiMenuBar() || TopLevelMenuExists(ctx, kScratchHelp);
		const bool englishGone = !ImGuiMenuBar() || !TopLevelMenuExists(ctx, labelBefore.c_str());

		// Switch back.
		CTemplateAppI18n::SetActive(before);
		view->menu->needsRebuild = true;
		ctx->Yield(3);
		const bool englishBack = !ImGuiMenuBar() || TopLevelMenuExists(ctx, labelBefore.c_str());
		const bool translatedGone = !ImGuiMenuBar() || !TopLevelMenuExists(ctx, kScratchHelp);

		if (hadSaved)
			gApplicationDefaultConfig->SetStdString("locale", saved);
		else
		{
			gApplicationDefaultConfig->hjsonRoot.erase("locale");
			gApplicationDefaultConfig->SaveConfig();
		}

		IM_CHECK_NO_RET(switched);
		IM_CHECK_NO_RET(rebuilt);
		IM_CHECK_NO_RET(translatedShown);
		IM_CHECK_NO_RET(englishGone);
		IM_CHECK_NO_RET(englishBack);
		IM_CHECK_NO_RET(translatedGone);
		IM_CHECK(mgr->GetActiveLocale() == before);
	};

	t = IM_REGISTER_TEST(engine, "ui", "new_workspace_rejects_duplicate_name");
	t->TestFunc = [](ImGuiTestContext *ctx)
	{
		CViewTemplateAppMain *view = MainView();
		IM_CHECK(view != nullptr);
		IM_CHECK(view->IsWorkspaceNameTaken("") == true);     // empty is never valid
		const char *name = "__template_test_layout__";
		IM_CHECK(view->IsWorkspaceNameTaken(name) == false);

		// A layout with that name, added to the list only: AddLayout() would
		// register a shortcut and StoreLayouts() would persist it.
		CLayoutData *layout = new CLayoutData();
		layout->layoutName = STRALLOC(name);
		guiMain->layoutManager->layouts.push_back(layout);
		const bool taken = view->IsWorkspaceNameTaken(name);
		guiMain->layoutManager->layouts.remove(layout);
		delete layout;
		IM_CHECK(taken == true);
		IM_CHECK(view->IsWorkspaceNameTaken(name) == false);
	};
}
#endif
