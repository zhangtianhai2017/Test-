using UnrealBuildTool;

public class BikiniValidatorEditorTarget : TargetRules
{
	public BikiniValidatorEditorTarget(TargetInfo Target) : base(Target)
	{
		Type = TargetType.Editor;
		DefaultBuildSettings = BuildSettingsVersion.V5;
		IncludeOrderVersion = EngineIncludeOrderVersion.Latest;
		ExtraModuleNames.Add("BikiniValidator");
	}
}
