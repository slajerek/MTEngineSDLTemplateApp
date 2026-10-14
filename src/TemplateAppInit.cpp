#include "TemplateAppInit.h"
#include "DBG_Log.h"
#include "CGuiMain.h"
#include "MT_API.h"
#include "SYS_CommandLine.h"
#include <SDL3/SDL_hints.h>
#include "CViewTemplateAppMain.h"
#include "CMTNativeMenuBar.h"
#include "CTemplateAppMenu.h"
#include "CTemplateAppI18n.h"
#include "CTemplateAppTestSuite.h"
#include "CTestRunner.h"
#include "MT_UiScale.h"        // MT_DetectDisplayUiScale / MT_SetUiScale
#include "SYS_DefaultConfig.h"   // gApplicationDefaultConfig

#if MT_ENABLE_IMGUI_TEST_ENGINE
#include "CImGuiTestEngine.h"
#include "imgui_te_engine.h"
extern void RegisterTemplateAppTests(ImGuiTestEngine *engine);
static bool sRunTests = false;
static int sWarmupFrames = 0;
static bool sTestsDone = false;
#endif

static bool sRunSuiteAll = false;
static bool sRunSuiteTest = false;
static bool sExitAfterTests = false;
static const char *sSuiteTestName = NULL;
static bool sSuiteTestScheduled = false;
static int sSuiteWarmupFrames = 0;

// ImGui: the ImGui menu bar on every platform. Native: native on macOS and
// Windows, ImGui on Linux. Only the engine creates the bar (CLAUDE.md, Menu).
// Wayland matches the window to platform/Linux/<app id>.desktop by app_id.
static const char *kAppId = "com.example.templateapp";

static const EMTMenuBarMode kMenuBarMode = EMTMenuBarMode::ImGui;

static CViewTemplateAppMain *sViewMain = nullptr;

static const char *kWindowTitle    = "TemplateApp";
static const char *kSettingsFolder = "MTEngineSDLTemplateApp";

const char *MT_GetMainWindowTitle()    { return kWindowTitle; }
const char *MT_GetSettingsFolderName() { return kSettingsFolder; }

void MT_GetDefaultWindowPositionAndSize(int *defaultWindowPosX, int *defaultWindowPosY, int *defaultWindowWidth, int *defaultWindowHeight, bool *maximized)
{
	// 640x480 is a FIXED PIXEL CONSTANT, so on a HiDPI display it has to grow
	// with everything else -- otherwise the first-run window is half the size
	// the author meant and the scaled UI immediately overflows it. The engine
	// asks for this during VID_Init, before there is a window and before
	// TemplateAppResolveUiScale() runs, so the answer comes from the primary
	// display rather than from the resolved setting; that is where a first-run
	// window lands anyway.
	//
	// First run only: once the window has been moved or resized the engine's
	// stored MainWindow* keys replace these.
	const float scale = MT_DetectDisplayUiScale();

	*defaultWindowPosX = SDL_WINDOWPOS_CENTERED;
	*defaultWindowPosY = SDL_WINDOWPOS_CENTERED;
	*defaultWindowWidth = (int)(640 * scale);
	*defaultWindowHeight = (int)(480 * scale);
	*maximized = false;
}

// ---------------------------------------------------------------------------
// The HiDPI UI scale, resolved once at startup.
//
// SDL3 declares PER_MONITOR_AWARE_V2 for the process, so on Windows and Linux
// the app is handed real physical pixels and nothing scales the UI unless the
// app says so. macOS is the opposite: SDL reports points and the OS already
// scaled. MT_DetectDisplayUiScale() knows that asymmetry so no app has to; see
// MTEngineSDL/docs/hidpi-ui-scaling.md.
//
// Auto-detect on first run, the user's choice ever after: GetFloat() returns
// its default only when ui.guiScale is absent, so the detected scale is passed
// as that default.
//
// Headless is pinned to 1.0 whatever the settings say, so a suite that asserts
// on pixel geometry does not move with the build machine's monitor or with a
// scale stored by an interactive session.
//
// MT_SetUiScale() scales text and geometry and re-applies the theme; it is
// idempotent. Called before the first view is constructed, so every
// MT_UiScaled() constant a view writes in its constructor is already right.
// ---------------------------------------------------------------------------
static void TemplateAppResolveUiScale()
{
	if (gHeadlessMode)
	{
		MT_SetUiScale(1.0f);
		LOGM("TemplateAppResolveUiScale: 1.00 (headless, pinned)");
		return;
	}

	float scale = MT_DetectDisplayUiScale();
	if (gApplicationDefaultConfig != NULL)
		gApplicationDefaultConfig->GetFloat("ui.guiScale", &scale, scale);

	MT_SetUiScale(scale);
	LOGM("TemplateAppResolveUiScale: %.2f", MT_GetUiScale());
}

// Test CLI flags: --run-test <name>, --run-suite, --exit-after-tests and,
// with the test engine compiled in, --run-tests.
static void TemplateAppParseTestFlags()
{
	for (int i = 0; i < (int)sysCommandLineArguments.size(); i++)
	{
		const char *arg = sysCommandLineArguments[i];
		if (strcmp(arg, "--run-test") == 0 && i + 1 < (int)sysCommandLineArguments.size())
		{
			sRunSuiteTest = true;
			sSuiteTestName = sysCommandLineArguments[++i];
		}
		else if (strcmp(arg, "--run-suite") == 0)
		{
			sRunSuiteAll = true;
		}
		else if (strcmp(arg, "--exit-after-tests") == 0)
		{
			sExitAfterTests = true;
		}
#if MT_ENABLE_IMGUI_TEST_ENGINE
		else if (strcmp(arg, "--run-tests") == 0)
		{
			sRunTests = true;
		}
#endif
	}
}

// Schedules the CTestSuite run and the ImGui tests requested on the command
// line. Both start after a few warmup frames, so the main view is ready.
static void TemplateAppScheduleTests()
{
	if (sRunSuiteAll || sRunSuiteTest)
	{
		sSuiteWarmupFrames = 3;
		sSuiteTestScheduled = true;
	}

#if MT_ENABLE_IMGUI_TEST_ENGINE
	if (sRunTests)
	{
		CImGuiTestEngine::Init();
		RegisterTemplateAppTests(CImGuiTestEngine::GetEngine());
		sWarmupFrames = 5;
	}
#endif
}

void MT_PreInit()
{
	SDL_SetHint(SDL_HINT_APP_ID, kAppId);
	SYS_SetMenuBarMode(kMenuBarMode);
}

void MT_GuiPreInit()
{
}

void MT_PostInit()
{
	LOGM("MT_PostInit");
	TemplateAppParseTestFlags();
	CTemplateAppI18n::Init();
	TemplateAppResolveUiScale();

	CViewTemplateAppMain *viewMain = new CViewTemplateAppMain(50, 50, 640 + 50, 480 + 50);
	guiMain->SetView(viewMain);
	sViewMain = viewMain;
	// Null in Native mode on headless macOS: the app then runs without a menu.
	viewMain->menu->Setup(guiMain->nativeMenuBar);

	TemplateAppScheduleTests();
	LOGM("TemplateApp initialized");
}

void MT_Render()
{
	// CTestSuite: run after warmup frames
	if (sSuiteTestScheduled && sSuiteWarmupFrames > 0)
	{
		sSuiteWarmupFrames--;
		if (sSuiteWarmupFrames == 0)
		{
			sSuiteTestScheduled = false;
			if (sRunSuiteAll)
				CTemplateAppTestSuite::RunFromCLI(NULL);
			else if (sRunSuiteTest)
				CTemplateAppTestSuite::RunFromCLI(sSuiteTestName);

			if (sExitAfterTests)
				SYS_Shutdown();
		}
	}

#if MT_ENABLE_IMGUI_TEST_ENGINE
	if (sRunTests && sWarmupFrames > 0)
	{
		sWarmupFrames--;
		if (sWarmupFrames == 0)
			CImGuiTestEngine::QueueAllTests();
	}

	if (sRunTests && sWarmupFrames == 0 && !sTestsDone)
	{
		if (CImGuiTestEngine::IsTestQueueEmpty())
		{
			sTestsDone = true;
			int tested = 0, success = 0;
			CImGuiTestEngine::GetResultSummary(&tested, &success);
			LOGM("ImGui tests: %d/%d passed", success, tested);
			// Write the same results file the CTestSuite path writes, so
			// tests/run_test.sh and CI parse one format for both suites.
			CImGuiTestEngine::WriteResults();
			if (sExitAfterTests)
				SYS_Shutdown();
		}
	}
#endif
}

void MT_PostRenderEndFrame()
{
	// Dynamic menu state is synced here, never in MT_Render(): mutating a Win32
	// menu inside a live ImGui frame can re-enter VID_Render() (CLAUDE.md, Menu).
	if (sViewMain && sViewMain->menu)
		sViewMain->menu->Sync();

#if MT_ENABLE_IMGUI_TEST_ENGINE
	if (sRunTests)
		CImGuiTestEngine::PostSwap();
#endif
}

void MT_Shutdown()
{
	LOGD("MT_Shutdown");
}

ImU32 ImPlotColorsExtensionGetterCallback(int index)
{
	(void)index;
	return 0;
}
