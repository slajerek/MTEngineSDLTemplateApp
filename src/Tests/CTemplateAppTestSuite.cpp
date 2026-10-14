#include "CTemplateAppTestSuite.h"
#include "CTestI18nLocales.h"
#include "CTestAppStartup.h"
#include "CTestMenuBarMode.h"

CTemplateAppTestSuite::CTemplateAppTestSuite()
{
	defaultTestTimeoutSeconds = 30;
	suiteTimeoutSeconds = 120;
}

CTemplateAppTestSuite::~CTemplateAppTestSuite()
{
}

void CTemplateAppTestSuite::RegisterTests()
{
	tests.push_back(std::make_unique<CTestI18nLocales>());
	tests.push_back(std::make_unique<CTestMenuBarMode>());
	tests.push_back(std::make_unique<CTestAppStartup>());
}

void CTemplateAppTestSuite::RunFromCLI(const char *testName)
{
	CTemplateAppTestSuite *suite = new CTemplateAppTestSuite();
	CTestSuite::RunFromCLI(suite, testName);
}
