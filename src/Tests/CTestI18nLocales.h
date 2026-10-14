#ifndef _CTESTI18NLOCALES_H_
#define _CTESTI18NLOCALES_H_

#include "CTest.h"

// Locales are data: every assets/locale/*.json is registered from its meta block.
class CTestI18nLocales : public CTest
{
public:
	virtual const char *GetName() override { return "I18nLocales"; }
	virtual void Run(ITestCallback *callback) override;
	virtual void Cancel() override {}
};

#endif
