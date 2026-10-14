#include "CTestI18nLocales.h"
#include "CTemplateAppI18n.h"
#include "CI18nManager.h"
#include "DBG_Log.h"
#include <filesystem>
#include <fstream>

void CTestI18nLocales::Run(ITestCallback *callback)
{
	this->callback = callback;
	isRunning = true;
	CI18nManager *mgr = CI18nManager::Instance();

	// en is registered by Init() from assets/locale/en.json.
	bool hasEn = false;
	for (const SI18nLocale &l : mgr->GetRegisteredLocales())
		if (l.tag == "en" && l.displayName == "English") hasEn = true;
	StepCompleted(1, hasEn, "en registered from en.json meta");
	if (!hasEn) { TestCompleted(false, "en not registered from its meta block"); return; }

	// A second file in a scratch dir is picked up with no code change.
	// The scratch locale is "zz", a tag no app ships: RegisterLocale() replaces a
	// locale with the same tag (CI18nManager.cpp:187-202) and LoadStrings()
	// merges into its table, so a real tag ("pl", shipped by the CiHybrid
	// preset) would leave test strings in production state for the rest of the
	// process.
	std::filesystem::path dir = std::filesystem::temp_directory_path() / "templateapp-i18n-test";
	std::filesystem::create_directories(dir);
	{
		std::ofstream f(dir / "zz.json");
		f << R"({"meta":{"locale":"zz","displayName":"Scratch","fallbacks":["en"],)"
		     R"("numberFormat":{"decimalSeparator":",","thousandsSeparator":" ","groupingSize":3},"version":1},)"
		     R"("strings":{"menu.file":"Plik"}})";
	}
	const int loaded = CTemplateAppI18n::LoadLocalesFromDir(dir.string() + "/");
	StepCompleted(2, loaded == 1, "one locale loaded from a scratch dir");

	const std::string before = mgr->GetActiveLocale();
	mgr->SetActiveLocale("zz");
	const bool translated = std::string(_T("menu.file")) == "Plik";
	const bool fallback = std::string(_T("menu.help")) == "Help";
	mgr->SetActiveLocale(before);
	std::filesystem::remove_all(dir);

	StepCompleted(3, translated, "zz string resolves");
	StepCompleted(4, fallback, "missing zz string falls back to en");

	// An unregistered tag (a stale saved setting, a removed locale file) is
	// never activated: SetActive falls back to en.
	const std::string beforeMissing = mgr->GetActiveLocale();
	CTemplateAppI18n::SetActive("xx-missing");
	const bool missingFallsBack = mgr->GetActiveLocale() == "en";
	CTemplateAppI18n::SetActive(beforeMissing);
	StepCompleted(5, missingFallsBack, "unregistered tag falls back to en");

	TestCompleted(loaded == 1 && translated && fallback && missingFallsBack, "locales are data-driven");
}
