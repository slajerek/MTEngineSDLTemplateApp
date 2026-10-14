#ifndef _CVIEWTEMPLATEAPPMAIN_H_
#define _CVIEWTEMPLATEAPPMAIN_H_

#include "CGuiView.h"

class CTemplateAppMenu;

class CViewTemplateAppMain : public CGuiView
{
public:
	CViewTemplateAppMain(float posX, float posY, float sizeX, float sizeY);
	virtual ~CViewTemplateAppMain();

	virtual void RenderImGui() override;
	virtual bool KeyDown(u32 keyCode, bool isShift, bool isAlt, bool isControl, bool isSuper) override;

	// Set by menu actions (from any backend, inside or outside the ImGui
	// frame); the windows themselves are opened in RenderImGui().
	bool showAbout = false, showImGuiMetrics = false, showImGuiDemo = false, showImGuiAbout = false;
	bool openNewWorkspace = false;

	CTemplateAppMenu *menu = nullptr;

	// Empty names and names already used by a workspace are taken.
	bool IsWorkspaceNameTaken(const char *name) const;

private:
	void RenderWindows();
	void RenderNewWorkspacePopup();

	char layoutName[128] = {0};
	bool doNotUpdateViewsPosition = false;
	bool nameTaken = false;
};

#endif
