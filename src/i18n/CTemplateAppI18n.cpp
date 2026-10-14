#include "CTemplateAppI18n.h"
#include "CI18nManager.h"
#include "RES_ResourceManager.h"
#include "SYS_DefaultConfig.h"
#include "DBG_Log.h"
#include "json.hpp"
#include <filesystem>
#include <fstream>
#include <vector>
#include <algorithm>

int CTemplateAppI18n::LoadLocalesFromDir(const std::string &dir)
{
	CI18nManager *mgr = CI18nManager::Instance();

	std::vector<std::filesystem::path> files;
	std::error_code ec;
	for (const auto &e : std::filesystem::directory_iterator(dir, ec))
		if (e.is_regular_file() && e.path().extension() == ".json")
			files.push_back(e.path());
	std::sort(files.begin(), files.end());   // deterministic menu order

	int loaded = 0;
	for (const auto &path : files)
	{
		std::ifstream in(path);
		nlohmann::json doc = nlohmann::json::parse(in, nullptr, /*allow_exceptions*/ false);
		if (doc.is_discarded() || !doc.contains("meta") || !doc["meta"].contains("locale"))
		{
			LOGError("CTemplateAppI18n: %s has no meta.locale, skipped", path.string().c_str());
			continue;
		}
		const nlohmann::json &meta = doc["meta"];

		SI18nLocale locale;
		locale.tag         = meta["locale"].get<std::string>();
		locale.displayName = meta.value("displayName", locale.tag);
		if (meta.contains("fallbacks"))
			for (const auto &f : meta["fallbacks"]) locale.explicitFallbacks.push_back(f.get<std::string>());
		if (locale.tag != "en" && std::find(locale.explicitFallbacks.begin(), locale.explicitFallbacks.end(), "en") == locale.explicitFallbacks.end())
			locale.explicitFallbacks.push_back("en");
		locale.cardinalRule = CI18nManager::GetBuiltinCardinalRule(locale.tag);
		locale.ordinalRule  = CI18nManager::GetBuiltinOrdinalRule(locale.tag);
		if (meta.contains("numberFormat"))
		{
			const nlohmann::json &nf = meta["numberFormat"];
			locale.numberFormat.decimalSeparator   = nf.value("decimalSeparator", std::string("."));
			locale.numberFormat.thousandsSeparator = nf.value("thousandsSeparator", std::string(","));
			locale.numberFormat.groupingSize       = nf.value("groupingSize", 3);
		}

		mgr->RegisterLocale(locale);
		if (mgr->LoadStrings(locale.tag, path.string()))
			loaded++;
		else
			LOGError("CTemplateAppI18n: LoadStrings failed for %s", path.string().c_str());
	}
	return loaded;
}

void CTemplateAppI18n::Init()
{
	std::string dir = RES_ResolveResourceDir("assets/locale/", "en.json");
	int n = LoadLocalesFromDir(dir);

	const char *saved = "en";
	gApplicationDefaultConfig->GetString("locale", &saved, "en");
	const std::string active = RegisteredOrEnglish(saved);
	CI18nManager::Instance()->SetActiveLocale(active);
	LOGM("CTemplateAppI18n::Init: %d locales, active %s", n, active.c_str());
}

std::string CTemplateAppI18n::RegisteredOrEnglish(const std::string &tag)
{
	// A saved tag whose file is gone (or a typo) must not become the active
	// locale: every lookup would fall through to keys.
	if (CI18nManager::Instance()->GetLocale(tag) != nullptr)
		return tag;
	LOGM("CTemplateAppI18n: locale '%s' is not registered, using en", tag.c_str());
	return "en";
}

void CTemplateAppI18n::SetActive(const std::string &tag)
{
	const std::string active = RegisteredOrEnglish(tag);
	CI18nManager::Instance()->SetActiveLocale(active);
	gApplicationDefaultConfig->SetString("locale", active.c_str());
}
