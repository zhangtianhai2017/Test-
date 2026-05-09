using UnrealBuildTool;

public class BikiniValidator : ModuleRules
{
	public BikiniValidator(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;

		PublicDependencyModuleNames.AddRange(new string[] {
			"Core",
			"CoreUObject",
			"Engine",
			"InputCore",
			"EnhancedInput",
			"HTTP",
			"Json",
			"JsonUtilities",
			"UMG",
			"Slate",
			"SlateCore",
			"glTFRuntime"
		});

		PrivateDependencyModuleNames.AddRange(new string[] { });
	}
}
