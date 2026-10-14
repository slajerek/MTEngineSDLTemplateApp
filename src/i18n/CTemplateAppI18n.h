#ifndef _CTEMPLATEAPPI18N_H_
#define _CTEMPLATEAPPI18N_H_

#include <string>

// Locales are data. Every assets/locale/<tag>.json is registered from its
// "meta" block; plural rules come from the engine's CLDR tables. Adding a
// language is adding a file.
class CTemplateAppI18n
{
public:
	static void Init();

	// Registers and loads every *.json in dir (with trailing slash).
	// Returns the number of locales loaded.
	static int LoadLocalesFromDir(const std::string &dir);

	// Activates a registered locale and persists it ("locale" setting).
	// An unregistered tag activates "en" instead.
	static void SetActive(const std::string &tag);

	// tag when it is registered, otherwise "en".
	static std::string RegisteredOrEnglish(const std::string &tag);
};

#endif
