"""
检查当前配置
"""
from app.config import get_settings

settings = get_settings()

print("=" * 60)
print("Current Trajectory Configuration:")
print("=" * 60)
print(f"enable_agent_trajectory:      {settings.enable_agent_trajectory}")
print(f"save_trajectory_to_file:       {settings.save_trajectory_to_file}")
print(f"trajectory_log_dir:            {settings.trajectory_log_dir}")
print(f"enable_langchain_callbacks:    {settings.enable_langchain_callbacks}")
print(f"callback_capture_thoughts:     {settings.callback_capture_thoughts}")
print(f"callback_capture_actions:      {settings.callback_capture_actions}")
print(f"callback_capture_results:      {settings.callback_capture_results}")
print("=" * 60)
