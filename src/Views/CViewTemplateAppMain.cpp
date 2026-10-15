#include "CViewTemplateAppMain.h"
#include "CTemplateAppMenu.h"
#include "CGuiMain.h"
#include "CLayoutManager.h"
#include "CI18nManager.h"
#include "TemplateAppVersion.h"
#include "SYS_Main.h"
#include "DBG_Log.h"
#include "imgui.h"
#include <cstring>
#include <string>

CViewTemplateAppMain::CViewTemplateAppMain(float posX, float posY, float sizeX, float sizeY)
: CGuiView("CViewTemplateAppMain", posX, posY, -1, sizeX, sizeY)
{
	imGuiNoWindowPadding = false;
	imGuiNoScrollbar = false;
	menu = new CTemplateAppMenu(this);
}

CViewTemplateAppMain::~CViewTemplateAppMain()
{
}

void CViewTemplateAppMain::RenderImGui()
{
	menu->RunPendingAction();   // what a menu item asked for, now inside the frame
	PreRenderImGui();
	// Your app starts here.
	PostRenderImGui();

	RenderWindows();
	RenderNewWorkspacePopup();
}

bool CViewTemplateAppMain::IsWorkspaceNameTaken(const char *name) const
{
	if (name == nullptr || name[0] == 0)
		return true;
	for (CLayoutData *l : guiMain->layoutManager->layouts)
		if (l->layoutName && strcmp(l->layoutName, name) == 0)
			return true;
	return false;
}

void CViewTemplateAppMain::RenderWindows()
{
	if (showAbout)
	{
		const std::string title = std::string(_T("about.title")) + "###TemplateAppAbout";
		if (ImGui::Begin(title.c_str(), &showAbout, ImGuiWindowFlags_AlwaysAutoResize))
		{
			ImGui::TextUnformatted(_T("app.title"));
			ImGui::Text(_T("about.version"), TEMPLATEAPP_VERSION);
			ImGui::TextUnformatted(_T("about.engine"));
		}
		ImGui::End();
	}
	if (showImGuiMetrics) ImGui::ShowMetricsWindow(&showImGuiMetrics);
	if (showImGuiDemo)    ImGui::ShowDemoWindow(&showImGuiDemo);
	if (showImGuiAbout)   ImGui::ShowAboutWindow(&showImGuiAbout);
}

void CViewTemplateAppMain::RenderNewWorkspacePopup()
{
	const std::string popupId = std::string(_T("workspace.new.title")) + "###NewWorkspace";

	// Opened here, inside the ImGui frame: a native menu lambda runs outside it.
	// A native menu stays clickable while the modal is open: a second request
	// while a layout is pending is ignored, not leaked.
	if (openNewWorkspace && menu->pendingLayout != nullptr)
		openNewWorkspace = false;
	if (openNewWorkspace)
	{
		openNewWorkspace = false;
		menu->pendingLayout = new CLayoutData();
		guiMain->layoutManager->SerializeLayoutAsync(menu->pendingLayout);
		layoutName[0] = 0;
		doNotUpdateViewsPosition = false;
		nameTaken = false;
		ImGui::OpenPopup(popupId.c_str());
	}

	if (!ImGui::BeginPopupModal(popupId.c_str(), nullptr,
	        menu->waitingForShortcut ? ImGuiWindowFlags_NoResize : ImGuiWindowFlags_AlwaysAutoResize))
		return;

	if (menu->waitingForShortcut)
	{
		ImGui::TextUnformatted(_T("workspace.new.press_key"));
		ImGui::EndPopup();
		return;
	}

	bool save = ImGui::InputText(_TID("workspace.new.name", "NewWorkspace"), layoutName, sizeof(layoutName),
	                             ImGuiInputTextFlags_EnterReturnsTrue);
	ImGui::Checkbox(_T("workspace.new.no_update_positions"), &doNotUpdateViewsPosition);
	if (menu->pendingLayout->keyShortcut)
		ImGui::Text(_T("workspace.new.shortcut"), menu->pendingLayout->keyShortcut->cstr);
	if (ImGui::Button(_T("workspace.new.assign_shortcut")))
		menu->waitingForShortcut = true;
	if (nameTaken)
		ImGui::TextUnformatted(_T("workspace.new.name_taken"));

	if (ImGui::Button(_T("workspace.new.cancel")))
	{
		delete menu->pendingLayout;
		menu->pendingLayout = nullptr;
		ImGui::CloseCurrentPopup();
	}
	ImGui::SameLine();
	if (ImGui::Button(_T("workspace.new.create")))
		save = true;

	if (save && menu->pendingLayout)
	{
		// Names are ImGui IDs in the workspace menu: duplicates are refused.
		nameTaken = IsWorkspaceNameTaken(layoutName);
		if (!nameTaken)
		{
			CLayoutData *layout = menu->pendingLayout;
			layout->layoutName = STRALLOC(layoutName);
			layout->doNotUpdateViewsPositions = doNotUpdateViewsPosition;
			if (layout->keyShortcut)
			{
				// SetName takes char * and copies it.
				char *shortcutName = SYS_GetCharBuf();
				snprintf(shortcutName, MAX_STRING_LENGTH, "Workspace %s", layoutName);   // identity, not UI text: never translated
				layout->keyShortcut->SetName(shortcutName);
				SYS_ReleaseCharBuf(shortcutName);
			}
			guiMain->layoutManager->AddLayout(layout);
			guiMain->layoutManager->currentLayout = layout;
			guiMain->layoutManager->StoreLayouts();
			menu->pendingLayout = nullptr;
			ImGui::CloseCurrentPopup();
		}
	}
	ImGui::EndPopup();
}

bool CViewTemplateAppMain::KeyDown(u32 keyCode, bool isShift, bool isAlt, bool isControl, bool isSuper)
{
	if (menu->KeyDown(keyCode, isShift, isAlt, isControl, isSuper))
		return true;
	return CGuiView::KeyDown(keyCode, isShift, isAlt, isControl, isSuper);
}
