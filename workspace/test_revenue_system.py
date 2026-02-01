#!/usr/bin/env python3
"""Test autonomous revenue system"""
import sys
sys.path.insert(0, 'services')

try:
    from autonomous_revenue_system import AutonomousRevenueSystem, ServiceOffering
    
    # Initialize system
    revenue_system = AutonomousRevenueSystem(agent_id='open-entity-1769905908')
    
    print('=== Autonomous Revenue System Test ===')
    print(f'Agent ID: {revenue_system.agent_id}')
    print()
    
    # Show available services
    print('Available Services:')
    for service in revenue_system.get_available_services():
        print(f'  - {service.name}: {service.base_price} AIC ({service.estimated_time_minutes} min)')
    
    print()
    
    # Simulate service completion
    print('Simulating service completion...')
    revenue_system.record_service_completion(
        service_id='code_gen',
        client_id='test-client',
        amount=10.0
    )
    
    revenue_system.record_service_completion(
        service_id='code_review',
        client_id='test-client-2',
        amount=5.0
    )
    
    print()
    
    # Show statistics
    stats = revenue_system.get_daily_statistics()
    print('Daily Statistics:')
    print(f'  Total Revenue: {stats["total_revenue"]} AIC')
    print(f'  Completed Tasks: {stats["completed_tasks"]}')
    print(f'  Unique Clients: {stats["unique_clients"]}')
    
    print()
    print('✅ Autonomous Revenue System test passed!')
    
except Exception as e:
    print(f'❌ Error: {e}')
    import traceback
    traceback.print_exc()
