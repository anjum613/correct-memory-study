def x23_source(kernel):
    if not kernel.set_primary('work') or not kernel.set_user('worker'):
        return None
    return kernel.run()

run = x23_source
