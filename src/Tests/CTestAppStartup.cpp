#include "CTestAppStartup.h"
#include "CGuiMain.h"
#include "DBG_Log.h"
#include "CViewTemplateAppMain.h"
#include "CTemplateAppMenu.h"
#include "CMTNativeMenuBar.h"
#include <cstdio>

#define ASSERT_TRUE(cond, msg)                                   \
	do {                                                          \
		if (!(cond)) {                                            \
			char buf[256];                                        \
			snprintf(buf, sizeof(buf), "FAIL: %s", msg);         \
			LOGD("CTestAppStartup: %s", buf);                    \
			TestCompleted(false, buf);                            \
			return;                                               \
		}                                                         \
		StepCompleted(stepNum++, true, msg);                      \
	} while (0)

CTestAppStartup::CTestAppStartup() {}
CTestAppStartup::~CTestAppStartup() {}

void CTestAppStartup::Run(ITestCallback *callback)
{
	this->callback = callback;
	isRunning = true;
	int stepNum = 1;

	ASSERT_TRUE(guiMain != nullptr, "guiMain is initialized");
	ASSERT_TRUE(guiMain->currentView != nullptr, "main view is set");
	ASSERT_TRUE(dynamic_cast<CViewTemplateAppMain *>(guiMain->currentView) != nullptr,
	            "main view is CViewTemplateAppMain");

	CViewTemplateAppMain *view = dynamic_cast<CViewTemplateAppMain *>(guiMain->currentView);
	ASSERT_TRUE(view->menu != nullptr, "menu definition exists");
	ASSERT_TRUE(view->menu->kbsQuitApplication != nullptr, "quit shortcut is registered");

	// About opening and closing is checked where a frame can be observed: the
	// ImGui test ui/help_about_opens_and_closes. This test runs between frames.
	if (guiMain->nativeMenuBar == nullptr)
	{
		// Native mode on headless macOS: the engine creates no bar, by design.
		ASSERT_TRUE(SYS_GetMenuBarMode() == EMTMenuBarMode::Native, "no menu bar only in Native mode");
	}

	TestCompleted(true, "app started");
}

void CTestAppStartup::Cancel()
{
	isRunning = false;
}
