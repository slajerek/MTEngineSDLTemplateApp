#ifndef _CTEMPLATEAPPTESTSUITE_H_
#define _CTEMPLATEAPPTESTSUITE_H_

#include "CTestSuite.h"

class CTemplateAppTestSuite : public CTestSuite
{
public:
	CTemplateAppTestSuite();
	virtual ~CTemplateAppTestSuite();

	virtual void RegisterTests() override;

	// Convenience: creates suite and calls CTestSuite::RunFromCLI
	static void RunFromCLI(const char *testName);
};

#endif
