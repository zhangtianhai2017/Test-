using UnrealBuildTool;

public class BikiniValidatorTarget : TargetRules
{
	public BikiniValidatorTarget(TargetInfo Target) : base(Target)
	{
		Type = TargetType.Game;
		DefaultBuildSettings = BuildSettingsVersion.V5;
		IncludeOrderVersion = EngineIncludeOrderVersion.Latest;
		ExtraModuleNames.Add("BikiniValidator");
	}
}
